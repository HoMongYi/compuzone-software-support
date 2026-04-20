<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';

	onMount(() => {
		document.documentElement.classList.remove('dark');
	});
</script>

<slot />
