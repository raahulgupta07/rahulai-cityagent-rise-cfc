<script lang="ts">const sw = [['bg','#F5F1EA'],['surface','#FFFDF9'],['ink','#2B2722'],['accent','#C96442'],['sage','#6F8F6A'],['warn','#C7913B'],['line','#E7E0D5']];</script>
<h1 class="text-3xl mb-6">Styleguide</h1>
<div class="flex gap-2 mb-6 flex-wrap">{#each sw as [n,c]}<div class="card text-center w-28"><div class="h-10 rounded-xl mb-2" style="background:{c}"></div><div class="text-xs">{n}</div></div>{/each}</div>
<div class="flex gap-3 mb-6 items-center"><button class="pill-accent">Primary</button><button class="pill-ghost">Ghost</button><span class="dot"></span></div>
<div class="card max-w-md"><h3 class="text-lg mb-1">Card</h3><p class="text-muted text-sm">Cream surface, hairline border, soft shadow, serif heading.</p></div>
