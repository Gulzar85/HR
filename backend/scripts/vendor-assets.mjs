// Copies pinned front-end libraries from node_modules into static/js/vendor (served same-origin, CSP-friendly).
import { copyFileSync, mkdirSync } from "node:fs";

const out = "static/js/vendor";
mkdirSync(out, { recursive: true });
const files = [
  ["node_modules/htmx.org/dist/htmx.min.js", "htmx.min.js"],
  ["node_modules/@alpinejs/csp/dist/cdn.min.js", "alpine.csp.min.js"],
  ["node_modules/lucide/dist/umd/lucide.min.js", "lucide.min.js"],
  ["node_modules/apexcharts/dist/apexcharts.min.js", "apexcharts.min.js"],
];
for (const [src, dst] of files) copyFileSync(src, `${out}/${dst}`);
console.log("vendored", files.length, "files");
