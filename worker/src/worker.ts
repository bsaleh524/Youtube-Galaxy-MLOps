// Test entry: loads the index from the ASSETS binding (worker/test/fixtures via wrangler.test.jsonc).
// Production uses src/main.ts, which bundles the index into the script instead.
import { createHandler } from "./handler";
import { getIndex } from "./index_loader";

export default createHandler(getIndex);
