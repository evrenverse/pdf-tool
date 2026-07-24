# Agent evals

The eval generates a synthetic PDF and exercises the real installed CLI:

1. discover document structure;
2. locate a label;
3. perform a bounded read;
4. add an overlay transactionally;
5. verify the output contains the overlay text.

```bash
uv run python evals/run_evals.py
```

The runner emits one JSON result and exits nonzero on failure. It never uses
external documents or network services.
