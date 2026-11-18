import { sources } from "../lib/catalog.mjs";
import Studio from "./studio";

export default function Page() {
  const catalog = sources.map(({ id, product, file }) => ({ id, product, file }));
  return <Studio catalog={catalog} />;
}
