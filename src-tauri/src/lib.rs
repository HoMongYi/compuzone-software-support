use std::sync::Mutex;

pub struct DbState(pub Mutex<Option<String>>);

pub mod commands {
    use rusqlite::{params, Connection};
    use serde::{Deserialize, Serialize};
    use tauri::State;

    use crate::DbState;

    #[derive(Serialize, Deserialize, Clone)]
    pub struct Product {
        pub product_no: i64,
        pub product_name: String,
        pub scraped_at: Option<String>,
        pub software_url: Option<String>,
        pub is_verified: Option<i64>,
        pub ai_note: Option<String>,
        pub updated_at: Option<String>,
        pub user_approved: Option<i64>,
    }

    #[derive(Serialize)]
    pub struct Stats {
        pub total: i64,
        pub has_url: i64,
        pub no_software: i64,
        pub error_count: i64,
        pub unprocessed: i64,
        pub pending_review: i64,
        pub approved: i64,
        pub rejected: i64,
    }

    #[derive(Serialize)]
    pub struct ProductPage {
        pub items: Vec<Product>,
        pub total: i64,
        pub page: i64,
        pub page_size: i64,
    }

    fn open_conn(db_path: &str) -> Result<Connection, String> {
        let conn = Connection::open(db_path).map_err(|e| e.to_string())?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
            .map_err(|e| e.to_string())?;
        Ok(conn)
    }

    fn migrate(conn: &Connection) -> Result<(), String> {
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS products (
                product_no   INTEGER PRIMARY KEY,
                product_name TEXT    NOT NULL,
                scraped_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS software_support (
                product_no   INTEGER PRIMARY KEY REFERENCES products(product_no),
                software_url TEXT,
                is_verified  INTEGER DEFAULT 0,
                ai_note      TEXT,
                updated_at   TEXT
            );",
        )
        .map_err(|e| e.to_string())?;

        let has_col: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('software_support') WHERE name='user_approved'",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);

        if has_col == 0 {
            conn.execute_batch(
                "ALTER TABLE software_support ADD COLUMN user_approved INTEGER DEFAULT NULL;",
            )
            .map_err(|e| e.to_string())?;
        }

        Ok(())
    }

    #[tauri::command]
    pub fn init_db(db_path: String, state: State<'_, DbState>) -> Result<(), String> {
        let conn = open_conn(&db_path)?;
        migrate(&conn)?;
        *state.0.lock().unwrap() = Some(db_path);
        Ok(())
    }

    #[tauri::command]
    pub fn get_stats(state: State<'_, DbState>) -> Result<Stats, String> {
        let guard = state.0.lock().unwrap();
        let path = guard.as_ref().ok_or("DB가 초기화되지 않았습니다")?;
        let conn = open_conn(path)?;

        let q = |sql: &str| -> Result<i64, String> {
            conn.query_row(sql, [], |r| r.get(0))
                .map_err(|e| e.to_string())
        };

        Ok(Stats {
            total: q("SELECT COUNT(*) FROM products")?,
            has_url: q("SELECT COUNT(*) FROM software_support WHERE is_verified = 1")?,
            no_software: q("SELECT COUNT(*) FROM software_support WHERE is_verified = 2")?,
            error_count: q("SELECT COUNT(*) FROM software_support WHERE is_verified = 3")?,
            unprocessed: q(
                "SELECT COUNT(*) FROM products p
                 LEFT JOIN software_support s ON p.product_no = s.product_no
                 WHERE s.product_no IS NULL OR s.is_verified = 0",
            )?,
            pending_review: q(
                "SELECT COUNT(*) FROM software_support WHERE is_verified = 1 AND user_approved IS NULL",
            )?,
            approved: q("SELECT COUNT(*) FROM software_support WHERE user_approved = 1")?,
            rejected: q("SELECT COUNT(*) FROM software_support WHERE user_approved = 0")?,
        })
    }

    #[tauri::command]
    pub fn get_products(
        filter: String,
        search: String,
        page: i64,
        page_size: i64,
        state: State<'_, DbState>,
    ) -> Result<ProductPage, String> {
        let guard = state.0.lock().unwrap();
        let path = guard.as_ref().ok_or("DB가 초기화되지 않았습니다")?;
        let conn = open_conn(path)?;

        let where_filter = match filter.as_str() {
            "has_url" => "s.is_verified = 1",
            "pending_review" => "s.is_verified = 1 AND s.user_approved IS NULL",
            "approved" => "s.user_approved = 1",
            "rejected" => "s.user_approved = 0",
            "no_software" => "s.is_verified = 2",
            "error" => "s.is_verified = 3",
            "unprocessed" => "(s.product_no IS NULL OR s.is_verified = 0)",
            _ => "1=1",
        };

        let safe_search = search.replace('\'', "''");
        let where_search = if safe_search.is_empty() {
            "1=1".to_string()
        } else {
            format!("p.product_name LIKE '%{safe_search}%'")
        };

        let count_sql = format!(
            "SELECT COUNT(*) FROM products p
             LEFT JOIN software_support s ON p.product_no = s.product_no
             WHERE ({where_filter}) AND ({where_search})"
        );
        let total: i64 = conn
            .query_row(&count_sql, [], |r| r.get(0))
            .map_err(|e| e.to_string())?;

        let offset = (page - 1) * page_size;
        let query_sql = format!(
            "SELECT p.product_no, p.product_name, p.scraped_at,
                    s.software_url, s.is_verified, s.ai_note, s.updated_at, s.user_approved
             FROM products p
             LEFT JOIN software_support s ON p.product_no = s.product_no
             WHERE ({where_filter}) AND ({where_search})
             ORDER BY
               CASE WHEN s.user_approved IS NULL THEN 0 ELSE 1 END,
               p.product_no DESC
             LIMIT {page_size} OFFSET {offset}"
        );

        let mut stmt = conn.prepare(&query_sql).map_err(|e| e.to_string())?;
        let items = stmt
            .query_map([], |row| {
                Ok(Product {
                    product_no: row.get(0)?,
                    product_name: row.get(1)?,
                    scraped_at: row.get(2)?,
                    software_url: row.get(3)?,
                    is_verified: row.get(4)?,
                    ai_note: row.get(5)?,
                    updated_at: row.get(6)?,
                    user_approved: row.get(7)?,
                })
            })
            .map_err(|e| e.to_string())?
            .collect::<Result<Vec<Product>, _>>()
            .map_err(|e| e.to_string())?;

        Ok(ProductPage {
            items,
            total,
            page,
            page_size,
        })
    }

    #[tauri::command]
    pub fn set_user_approved(
        product_no: i64,
        approved: Option<i64>,
        state: State<'_, DbState>,
    ) -> Result<(), String> {
        let guard = state.0.lock().unwrap();
        let path = guard.as_ref().ok_or("DB가 초기화되지 않았습니다")?;
        let conn = open_conn(path)?;

        let affected = conn
            .execute(
                "UPDATE software_support SET user_approved = ?1 WHERE product_no = ?2",
                params![approved, product_no],
            )
            .map_err(|e| e.to_string())?;

        if affected == 0 {
            return Err(format!(
                "product_no={product_no} 에 대한 software_support 레코드가 없습니다"
            ));
        }

        Ok(())
    }

    #[tauri::command]
    pub fn update_url(
        product_no: i64,
        software_url: String,
        state: State<'_, DbState>,
    ) -> Result<(), String> {
        let guard = state.0.lock().unwrap();
        let path = guard.as_ref().ok_or("DB가 초기화되지 않았습니다")?;
        let conn = open_conn(path)?;

        let affected = conn
            .execute(
                "UPDATE software_support SET software_url = ?1, is_verified = 1, updated_at = datetime('now','localtime') WHERE product_no = ?2",
                params![software_url, product_no],
            )
            .map_err(|e| e.to_string())?;

        if affected == 0 {
            return Err(format!(
                "product_no={product_no} 에 대한 software_support 레코드가 없습니다"
            ));
        }

        Ok(())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(DbState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            commands::init_db,
            commands::get_stats,
            commands::get_products,
            commands::set_user_approved,
            commands::update_url,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
