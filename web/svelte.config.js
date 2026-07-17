// Adapter is env-switchable:
//   default        -> adapter-static (SPA) — baked into the API image for single-container
//   ADAPTER=node   -> adapter-node — standalone Node server for the multi-container stacks
import adapterStatic from '@sveltejs/adapter-static';
import adapterNode from '@sveltejs/adapter-node';

const useNode = process.env.ADAPTER === 'node';

export default {
  kit: {
    adapter: useNode
      ? adapterNode()
      : adapterStatic({ fallback: 'index.html', strict: false })
  }
};
