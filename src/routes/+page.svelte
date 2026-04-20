<script lang="ts">
	import { onMount } from 'svelte';
	import { invoke } from '@tauri-apps/api/core';
	import { open as openShell } from '@tauri-apps/plugin-shell';

	const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
	const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

	async function rpc<T>(cmd: string, args: Record<string, unknown> = {}): Promise<T> {
		if (isTauri) return invoke<T>(cmd, args);
		switch (cmd) {
				case 'get_stats': {
				const res = await fetch(`${API_BASE}/stats`);
				if (!res.ok) throw await res.text();
				return res.json() as T;
			}
			case 'get_products': {
				const params = new URLSearchParams({
					filter: args.filter as string,
					search: args.search as string,
					page: String(args.page),
					page_size: String(args.pageSize)
				});
				const res = await fetch(`${API_BASE}/products?${params}`);
				if (!res.ok) throw await res.text();
				return res.json() as T;
			}
			case 'set_user_approved': {
				const res = await fetch(`${API_BASE}/set_user_approved`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ product_no: args.productNo, approved: args.approved ?? null })
				});
				if (!res.ok) throw await res.text();
				return {} as T;
			}
			case 'update_url': {
				const res = await fetch(`${API_BASE}/update_url`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ product_no: args.productNo, software_url: args.softwareUrl })
				});
				if (!res.ok) throw await res.text();
				return {} as T;
			}
			default:
				throw new Error(`Unknown command: ${cmd}`);
		}
	}

	async function openUrl(url: string) {
		if (isTauri) return openShell(url);
		window.open(url, '_blank');
	}

	interface Product {
		product_no: number;
		product_name: string;
		scraped_at: string | null;
		software_url: string | null;
		is_verified: number | null;
		ai_note: string | null;
		updated_at: string | null;
		user_approved: number | null;
	}

	interface Stats {
		total: number;
		has_url: number;
		no_software: number;
		error_count: number;
		unprocessed: number;
		pending_review: number;
		approved: number;
		rejected: number;
	}

	interface ProductPage {
		items: Product[];
		total: number;
		page: number;
		page_size: number;
	}

	let stats: Stats | null = $state(null);
	let productPage: ProductPage | null = $state(null);
	let filter = $state('pending_review');
	let search = $state('');
	let currentPage = $state(1);
	const pageSize = 50;
	let loading = $state(false);
	let errorMsg = $state('');
	let toastMsg = $state('');
	let toastType = $state<'ok' | 'err'>('ok');
	let searchTimer: ReturnType<typeof setTimeout>;

	let showUrlModal = $state(false);
	let rejectProductNo = $state<number | null>(null);
	let correctedUrl = $state('');

	let showHelpModal = $state(false);

	let showAddUrlModal = $state(false);
	let addUrlProductNo = $state<number | null>(null);
	let addUrlProductName = $state('');
	let addUrlValue = $state('');

	let showApproveModal = $state(false);
	let approveProductNo = $state<number | null>(null);
	let approveProductName = $state('');
	let approveProductUrl = $state<string | null>(null);

	const FILTER_OPTS = [
		{ value: 'pending_review', label: '🔍 검토대기' },
		{ value: 'all', label: '전체' },
		{ value: 'has_url', label: '🔗 URL있음' },
		{ value: 'approved', label: '✅ 승인됨' },
		{ value: 'rejected', label: '❌ 거부됨' },
		{ value: 'no_software', label: '⬜ 소프트웨어 없음' },
		{ value: 'error', label: '⚠️ 오류' },
		{ value: 'unprocessed', label: '⏳ 미처리' }
	];

	let totalPages = $derived(
		productPage != null ? Math.max(1, Math.ceil((productPage as ProductPage).total / pageSize)) : 1
	);
	let pageNumbers = $derived(
		Array.from({ length: Math.min(totalPages, 9) }, (_, i) => {
			if (totalPages <= 9) return i + 1;
			if (currentPage <= 5) return i + 1;
			if (currentPage >= totalPages - 4) return totalPages - 8 + i;
			return currentPage - 4 + i;
		})
	);

	async function refresh() {
		await Promise.all([loadStats(), loadProducts()]);
	}

	async function loadStats() {
		try {
			stats = await rpc<Stats>('get_stats');
		} catch (e) {
			errorMsg = String(e);
		}
	}

	async function loadProducts() {
		loading = true;
		try {
			productPage = await rpc<ProductPage>('get_products', {
				filter,
				search,
				page: currentPage,
				pageSize
			});
		} catch (e) {
			errorMsg = String(e);
		} finally {
			loading = false;
		}
	}

	function openApproveModal(productNo: number, productName: string, softwareUrl: string | null) {
		approveProductNo = productNo;
		approveProductName = productName;
		approveProductUrl = softwareUrl;
		showApproveModal = true;
	}

	function cancelApprove() {
		showApproveModal = false;
		approveProductNo = null;
		approveProductName = '';
		approveProductUrl = null;
	}

	async function confirmApprove() {
		if (approveProductNo === null) return;
		showApproveModal = false;
		const pno = approveProductNo;
		approveProductNo = null;
		approveProductName = '';
		approveProductUrl = null;
		await setApproval(pno, 1);
	}

	function openAddUrlModal(productNo: number, productName: string) {
		addUrlProductNo = productNo;
		addUrlProductName = productName;
		addUrlValue = '';
		showAddUrlModal = true;
	}

	function cancelAddUrl() {
		showAddUrlModal = false;
		addUrlProductNo = null;
		addUrlProductName = '';
		addUrlValue = '';
	}

	async function confirmAddUrl() {
		if (addUrlProductNo === null || !addUrlValue.trim()) return;
		showAddUrlModal = false;
		const pno = addUrlProductNo;
		const url = addUrlValue.trim();
		addUrlProductNo = null;
		addUrlProductName = '';
		addUrlValue = '';
		try {
			await rpc('update_url', { productNo: pno, softwareUrl: url });
			showToast('🔗 URL 저장됨', 'ok');
			await refresh();
		} catch (e) {
			showToast('오류: ' + String(e), 'err');
		}
	}

	function openRejectModal(productNo: number) {
		rejectProductNo = productNo;
		correctedUrl = '';
		showUrlModal = true;
	}

	function cancelReject() {
		showUrlModal = false;
		rejectProductNo = null;
		correctedUrl = '';
	}

	async function confirmReject() {
		if (rejectProductNo === null) return;
		showUrlModal = false;
		const pno = rejectProductNo;
		rejectProductNo = null;
		try {
			if (correctedUrl.trim()) {
				await rpc('update_url', { productNo: pno, softwareUrl: correctedUrl.trim() });
			}
			await setApproval(pno, 0);
		} catch (e) {
			showToast('오류: ' + String(e), 'err');
		}
		correctedUrl = '';
	}

	async function setApproval(productNo: number, approved: number | null) {
		try {
			await rpc('set_user_approved', { productNo, approved });
			showToast(approved === 1 ? '✅ 승인 저장' : approved === 0 ? '🔧 URL 수정' : '↩️ 초기화', 'ok');
			await refresh();
		} catch (e) {
			showToast('오류: ' + String(e), 'err');
		}
	}


	function onFilterChange(v: string) {
		filter = v;
		currentPage = 1;
		loadProducts();
	}

	function onSearchInput() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => {
			currentPage = 1;
			loadProducts();
		}, 350);
	}

	function goPage(p: number) {
		if (p < 1 || p > totalPages) return;
		currentPage = p;
		loadProducts();
	}

	function showToast(msg: string, type: 'ok' | 'err') {
		toastMsg = msg;
		toastType = type;
		setTimeout(() => (toastMsg = ''), 2000);
	}

	function verifiedBadge(v: number | null): { text: string; cls: string } {
		if (v === 1) return { text: 'URL있음', cls: 'bg-blue-100 text-blue-700 border-blue-200' };
		if (v === 2) return { text: '소프트웨어 없음', cls: 'bg-yellow-100 text-yellow-700 border-yellow-200' };
		if (v === 3) return { text: '오류', cls: 'bg-red-100 text-red-700 border-red-200' };
		return { text: '미처리', cls: 'bg-gray-100 text-gray-500 border-gray-200' };
	}

	onMount(async () => {
		await refresh();
	});
</script>

<!-- Toast -->
{#if toastMsg}
	<div
		class="fixed bottom-6 right-6 z-50 rounded-lg px-4 py-2.5 text-sm font-medium shadow-lg transition-all {toastType === 'ok' ? 'bg-gray-900 text-white' : 'bg-red-600 text-white'}"
	>
		{toastMsg}
	</div>
{/if}

<div class="flex h-screen flex-col bg-gray-50 font-sans text-gray-800">
	<!-- Header -->
	<header class="flex items-center gap-3 border-b border-gray-200 bg-white px-5 py-3 shadow-sm">
		<div class="flex items-center gap-2">
			<span class="text-xl font-bold text-blue-600">컴퓨존</span>
			<span class="text-lg font-semibold text-gray-700">스마트 소프트웨어 링크 서비스 관리툴</span>
		</div>
		<div class="ml-auto flex items-center gap-2">
			<button
				onclick={() => (showHelpModal = true)}
				class="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
				title="도움말"
			>
				❓ 도움말
			</button>
			<button
				onclick={refresh}
				class="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
				title="새로고침"
			>
				🔄
			</button>
		</div>
	</header>

	<!-- Stats row -->
		<div class="flex gap-3 border-b border-gray-200 bg-white px-5 py-3">
			{#if stats}
				{@const cards = [
					{ label: '전체 상품', value: stats.total, cls: 'text-gray-700' },
					{ label: 'URL 있음', value: stats.has_url, cls: 'text-blue-600' },
					{ label: '검토 대기', value: stats.pending_review, cls: 'text-orange-500' },
					{ label: '승인됨', value: stats.approved, cls: 'text-green-600' },
					{ label: '거부됨', value: stats.rejected, cls: 'text-red-500' },
					{ label: '소프트웨어 없음', value: stats.no_software, cls: 'text-yellow-600' },
					{ label: '오류', value: stats.error_count, cls: 'text-red-400' },
					{ label: '미처리', value: stats.unprocessed, cls: 'text-gray-400' }
				]}
				{#each cards as card}
					<div class="flex flex-col items-center rounded-lg border border-gray-100 bg-gray-50 px-5 py-2.5 text-center">
						<span class="text-2xl font-bold {card.cls}">{card.value.toLocaleString()}</span>
						<span class="text-sm text-gray-500">{card.label}</span>
					</div>
				{/each}
			{:else}
				<div class="text-sm text-gray-400">로딩 중...</div>
			{/if}
		</div>

		<!-- Filter + Search bar -->
		<div class="flex flex-wrap items-center gap-2 border-b border-gray-200 bg-white px-5 py-2.5">
			<div class="flex gap-1">
				{#each FILTER_OPTS as opt}
					<button
						onclick={() => onFilterChange(opt.value)}
						class="rounded-full border px-3 py-1.5 text-sm font-medium transition-colors {filter === opt.value
							? 'border-blue-500 bg-blue-500 text-white'
							: 'border-gray-200 bg-gray-50 text-gray-600 hover:bg-gray-100'}"
					>
						{opt.label}
					</button>
				{/each}
			</div>
			<div class="ml-auto flex items-center gap-2">
				<input
					type="search"
					placeholder="상품명 검색..."
					bind:value={search}
					oninput={onSearchInput}
					class="w-64 rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
				/>
				{#if productPage}
					<span class="whitespace-nowrap text-xs text-gray-400">
						총 {productPage.total.toLocaleString()}건
					</span>
				{/if}
			</div>
		</div>

		<!-- Table -->
		<div class="flex-1 overflow-auto">
			{#if loading}
				<div class="flex h-32 items-center justify-center">
					<div class="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
				</div>
			{:else if productPage && productPage.items.length === 0}
				<div class="flex h-32 flex-col items-center justify-center gap-1 text-gray-400">
					<span class="text-3xl">📭</span>
					<span class="text-sm">해당 조건의 상품이 없습니다</span>
				</div>
			{:else}
				<table class="w-full border-collapse text-sm">
					<thead class="sticky top-0 z-10 bg-gray-100 text-xs font-semibold uppercase tracking-wide text-gray-500">
						<tr>
							<th class="border-b border-gray-200 px-3 py-2.5 text-right">No.</th>
							<th class="border-b border-gray-200 px-3 py-2.5 text-left">상품명</th>
							<th class="w-24 border-b border-gray-200 px-3 py-2.5 text-center">AI 상태</th>
							<th class="min-w-[200px] border-b border-gray-200 px-3 py-2.5 text-left">소프트웨어 URL</th>
							<th class="min-w-[140px] border-b border-gray-200 px-3 py-2.5 text-left">AI 노트</th>
							<th class="min-w-[180px] border-b border-gray-200 px-4 py-2.5 text-center">검토</th>
						</tr>
					</thead>
					<tbody>
						{#if productPage}
							{#each productPage.items as p (p.product_no)}
								{@const badge = verifiedBadge(p.is_verified)}
								{@const reviewedYes = p.user_approved === 1}
								{@const reviewedNo = p.user_approved === 0}
								<tr
									class="border-b border-gray-100 transition-colors hover:bg-blue-50/40
										{reviewedYes ? 'bg-green-50/60' : reviewedNo ? 'bg-red-50/60' : 'bg-white'}"
								>
									<!-- product_no -->
									<td class="px-3 py-2 text-right font-mono text-xs text-gray-400">
										{p.product_no}
									</td>

									<!-- product_name -->
									<td class="min-w-[280px] px-3 py-2">
										<button
											type="button"
											class="block break-keep text-left font-medium text-blue-700 hover:underline"
											onclick={() => openUrl(`https://compuzone.co.kr/product/product_detail.htm?ProductNo=${p.product_no}`)}
										>
											{p.product_name}
										</button>
										{#if p.scraped_at}
											<span class="text-xs text-gray-400">{p.scraped_at.slice(0, 10)}</span>
										{/if}
									</td>

									<!-- AI 상태 badge -->
									<td class="w-24 px-3 py-2 text-center">
										<span
											class="inline-block rounded-full border px-2 py-0.5 text-xs font-medium {badge.cls}"
										>
											{badge.text}
										</span>
									</td>

									<!-- URL -->
									<td class="min-w-[200px] max-w-sm px-3 py-2">
										{#if p.software_url}
											<div class="flex items-center gap-1.5">
												<a
													href={p.software_url}
													onclick={(e) => {
														e.preventDefault();
														openUrl(p.software_url!);
													}}
													class="block max-w-xs truncate text-blue-600 hover:text-blue-800 hover:underline"
													title={p.software_url}
												>
													{p.software_url}
												</a>
												<button
													onclick={() => openUrl(p.software_url!)}
													class="shrink-0 text-gray-400 hover:text-blue-500"
													title="브라우저에서 열기"
												>
													↗
												</button>
											</div>
										{:else}
											{#if badge.text === '미처리'}
												<button
													onclick={() => openAddUrlModal(p.product_no, p.product_name)}
													class="rounded-lg border border-dashed border-blue-300 px-2.5 py-1 text-xs font-semibold text-blue-500 hover:bg-blue-50 hover:border-blue-400"
												>
													➕ URL 직접 추가
												</button>
											{:else}
												<span class="text-gray-300">—</span>
											{/if}
										{/if}
									</td>

									<!-- AI 노트 -->
									<td class="min-w-[140px] max-w-xs px-3 py-2">
										{#if p.ai_note}
											<span
												class="block truncate text-xs text-gray-500"
												title={p.ai_note}
											>
												{p.ai_note}
											</span>
										{:else}
											<span class="text-gray-300">—</span>
										{/if}
									</td>

									<!-- 검토 버튼 -->
									<td class="min-w-[160px] px-4 py-2">
										<div class="flex flex-nowrap items-center justify-center gap-1.5">
											{#if reviewedYes || reviewedNo}
												<!-- 이미 검토됨: 상태 표시 + 초기화 -->
												<span
													class="rounded-full px-2.5 py-1 text-xs font-bold {reviewedYes
														? 'bg-green-100 text-green-700'
														: 'bg-red-100 text-red-700'}"
												>
													{reviewedYes ? '✅ 예' : '❌ 아니요'}
												</span>
												<button
													onclick={() => setApproval(p.product_no, null)}
													class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-400 hover:border-gray-400 hover:text-gray-600"
													title="검토 초기화"
												>
													↩
												</button>
											{:else}
												<!-- 미검토: Yes/No 버튼 -->
												<button
													onclick={() => openApproveModal(p.product_no, p.product_name, p.software_url)}
													class="rounded-lg border border-green-300 bg-green-50 px-3 py-1.5 text-xs font-semibold text-green-700 hover:bg-green-100 active:bg-green-200"
												>
													✓ 예
												</button>
												<button
													onclick={() => openRejectModal(p.product_no)}
													class="rounded-lg border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 active:bg-red-200"
												>
													✗ 아니요
												</button>
											{/if}
										</div>
									</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			{/if}
		</div>

		<!-- Pagination -->
		{#if productPage && productPage.total > pageSize}
			<div class="flex items-center justify-between border-t border-gray-200 bg-white px-5 py-2.5">
				<span class="text-xs text-gray-500">
					페이지 {currentPage} / {totalPages} &nbsp;·&nbsp;
					총 {productPage.total.toLocaleString()}건
				</span>
				<div class="flex items-center gap-1">
					<button
						onclick={() => goPage(1)}
						disabled={currentPage === 1}
						class="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-30"
					>
						«
					</button>
					<button
						onclick={() => goPage(currentPage - 1)}
						disabled={currentPage === 1}
						class="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-30"
					>
						‹
					</button>
					{#each pageNumbers as pn}
						<button
							onclick={() => goPage(pn)}
							class="min-w-[28px] rounded px-2 py-1 text-xs {currentPage === pn
								? 'bg-blue-500 font-bold text-white'
								: 'text-gray-600 hover:bg-gray-100'}"
						>
							{pn}
						</button>
					{/each}
					<button
						onclick={() => goPage(currentPage + 1)}
						disabled={currentPage === totalPages}
						class="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-30"
					>
						›
					</button>
					<button
						onclick={() => goPage(totalPages)}
						disabled={currentPage === totalPages}
						class="rounded px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-30"
					>
						»
					</button>
				</div>
			</div>
		{/if}
</div>

{#if showApproveModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
		onkeydown={(e) => { if (e.key === 'Enter') confirmApprove(); if (e.key === 'Escape') cancelApprove(); }}
		role="dialog"
		tabindex="-1"
	>
		<div class="w-[800px] rounded-2xl bg-white p-6 shadow-2xl">
			<h3 class="mb-2 text-base font-bold text-gray-800">✅ 승인 확인</h3>
			<p class="mb-2 text-sm text-gray-600 break-keep">
				<span class="font-semibold text-gray-800">{approveProductName}</span>
			</p>
			{#if approveProductUrl}
				<a
					href={approveProductUrl}
					onclick={(e) => { e.preventDefault(); openUrl(approveProductUrl!); }}
					class="mb-3 flex items-center gap-1 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-600 hover:bg-blue-100 hover:underline"
					title={approveProductUrl}
				>
					<span class="shrink-0">🔗</span>
					<span class="truncate">{approveProductUrl}</span>
					<span class="ml-auto shrink-0">↗</span>
				</a>
			{/if}
			<p class="mb-5 text-base font-semibold text-blue-600">이 상품의 소프트웨어 URL을 승인하시겠습니까?</p>
			<div class="flex justify-end gap-2">
				<button
					onclick={cancelApprove}
					class="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
				>
					취소
				</button>
				<button
					onclick={confirmApprove}
					class="rounded-lg bg-green-500 px-4 py-2 text-sm font-semibold text-white hover:bg-green-600 active:bg-green-700"
				>
					✅ 승인
				</button>
			</div>
		</div>
	</div>
{/if}

{#if showUrlModal}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
		<div class="w-[460px] rounded-2xl bg-white p-6 shadow-2xl">
			<h3 class="mb-1 text-base font-bold text-gray-800">🔗 올바른 소프트웨어 URL 입력</h3>
			<p class="mb-4 text-xs text-gray-500">
				AI가 찾은 URL이 잘못된 경우 올바른 URL을 입력하세요.<br />
				비워두면 URL 없이 거부로 저장됩니다.
			</p>
			<input
				type="url"
				bind:value={correctedUrl}
				placeholder="https://example.com/driver..."
				class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
				onkeydown={(e) => e.key === 'Enter' && confirmReject()}
			/>
			<div class="mt-4 flex justify-end gap-2">
				<button
					onclick={cancelReject}
					class="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
				>
					취소
				</button>
				<button
					onclick={confirmReject}
					class="rounded-lg bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-600 active:bg-red-700"
				>
					🔧 URL 수정
				</button>
			</div>
		</div>
	</div>
{/if}

{#if showAddUrlModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
		onkeydown={(e) => { if (e.key === 'Enter') confirmAddUrl(); if (e.key === 'Escape') cancelAddUrl(); }}
		role="dialog"
		tabindex="-1"
	>
		<div class="w-[560px] rounded-2xl bg-white p-6 shadow-2xl">
			<h3 class="mb-1 text-base font-bold text-gray-800">➕ 소프트웨어 URL 직접 추가</h3>
			<p class="mb-1 text-sm font-semibold text-gray-700 break-keep">{addUrlProductName}</p>
			<p class="mb-4 text-xs text-gray-400">AI가 아직 분석하지 않은 상품에 직접 URL을 입력하여 저장합니다.</p>
			<input
				type="url"
				bind:value={addUrlValue}
				placeholder="https://example.com/driver..."
				class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
				onkeydown={(e) => e.key === 'Enter' && confirmAddUrl()}
			/>
			<div class="mt-4 flex justify-end gap-2">
				<button
					onclick={cancelAddUrl}
					class="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
				>
					취소
				</button>
				<button
					onclick={confirmAddUrl}
					disabled={!addUrlValue.trim()}
					class="rounded-lg bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600 active:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
				>
					🔗 URL 저장
				</button>
			</div>
		</div>
	</div>
{/if}

{#if showHelpModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
		onclick={() => (showHelpModal = false)}
		role="dialog"
		tabindex="-1"
		onkeydown={(e) => e.key === 'Escape' && (showHelpModal = false)}
	>
		<div
			class="w-[700px] max-h-[85vh] overflow-y-auto rounded-2xl bg-white p-7 shadow-2xl"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
			role="document"
		>
			<div class="mb-5 flex items-center justify-between">
				<h2 class="text-lg font-bold text-gray-800">❓ 사용 방법 및 기능 안내</h2>
				<button
					onclick={() => (showHelpModal = false)}
					class="rounded-full px-2 py-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 text-lg"
				>✕</button>
			</div>

			<div class="mb-5 rounded-xl bg-blue-50 px-5 py-4 text-sm text-blue-800">
				<p class="font-bold mb-1">📌 이 툴은 무엇인가요?</p>
				<p>컴퓨존에서 판매하는 상품 중 소프트웨어 및 드라이버 지원이 필요한 제품을 AI가 자동으로 분석하여 관련 소프트웨어 다운로드 링크를 찾아드립니다. 담당자는 이 툴에서 AI가 찾은 링크가 올바른지 검토하고 승인/거부합니다.</p>
			</div>

			<div class="mb-5">
				<p class="mb-2 font-bold text-gray-700">📊 상단 통계 카드</p>
				<table class="w-full text-sm border-collapse">
					<tbody>
						{#each [
							['전체 상품', 'DB에 등록된 전체 상품 수'],
							['URL 있음', 'AI가 소프트웨어 링크를 찾은 상품 수'],
							['검토 대기', 'AI가 URL을 찾았지만 아직 담당자가 검토하지 않은 상품 수'],
							['승인됨', '담당자가 ✓ 예를 눌러 URL이 올바르다고 확인한 상품 수'],
							['거부됨', '담당자가 ✗ 아니요를 눌러 URL이 잘못됐다고 표시한 상품 수'],
							['소프트웨어 없음', 'AI가 분석했지만 소프트웨어 지원이 불필요한 상품 수'],
							['오류', 'AI 분석 중 오류가 발생한 상품 수'],
							['미처리', '아직 AI가 분석하지 않은 상품 수'],
						] as [label, desc]}
							<tr class="border-b border-gray-100">
								<td class="w-32 py-2 font-semibold text-gray-700">{label}</td>
								<td class="py-2 text-gray-500">{desc}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<div class="mb-5">
				<p class="mb-2 font-bold text-gray-700">✅ 검토 방법 (순서대로)</p>
				<ol class="list-decimal pl-5 space-y-2 text-sm text-gray-600">
					<li>상단 필터에서 <span class="font-semibold text-orange-500">🔍 검토대기</span>를 선택합니다.</li>
					<li>목록에서 상품명과 AI가 찾은 소프트웨어 URL을 확인합니다.</li>
					<li>URL 링크를 클릭해 실제 페이지가 올바른지 확인합니다.</li>
					<li>올바르면 <span class="font-semibold text-green-600">✓ 예</span> → 확인 팝업에서 <strong>승인</strong>을 클릭합니다.</li>
					<li>잘못됐으면 <span class="font-semibold text-red-500">✗ 아니요</span> → 올바른 URL을 직접 입력하거나 비워두고 <strong>URL 수정</strong>을 클릭합니다.</li>
					<li>↩ 버튼으로 이미 검토한 항목을 검토 전 상태로 되돌릴 수 있습니다.</li>
				</ol>
			</div>

			<div class="mb-2">
				<p class="mb-2 font-bold text-gray-700">🔍 필터 버튼</p>
				<p class="text-sm text-gray-500">상단 필터 버튼으로 원하는 상태의 상품만 모아볼 수 있습니다. 상품명 검색도 함께 사용할 수 있습니다.</p>
			</div>

			<div class="mt-6 flex justify-end">
				<button
					onclick={() => (showHelpModal = false)}
					class="rounded-lg bg-blue-500 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-600"
				>
					확인
				</button>
			</div>
		</div>
	</div>
{/if}
