import { getStore } from "@netlify/blobs";
import crypto from "node:crypto";

const STORE = "babes";
const TOKEN_SECRET = process.env.TOKEN_SECRET || "dev-change-me-in-netlify-env";
const ADMIN_EMAILS = (process.env.ADMIN_EMAILS || "")
  .split(",")
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

function json(status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

function nowIso() {
  return new Date().toISOString();
}

function uid(prefix = "id") {
  return `${prefix}_${crypto.randomBytes(10).toString("hex")}`;
}

function normEmail(e) {
  return String(e || "").trim().toLowerCase();
}

function hashPassword(pw, salt = crypto.randomBytes(16).toString("hex")) {
  const dk = crypto.scryptSync(String(pw), salt, 64).toString("hex");
  return `scrypt:${salt}:${dk}`;
}

function verifyPassword(pw, stored) {
  if (!stored || !stored.startsWith("scrypt:")) return false;
  const [, salt, dk] = stored.split(":");
  const check = crypto.scryptSync(String(pw), salt, 64).toString("hex");
  try {
    return crypto.timingSafeEqual(Buffer.from(dk, "hex"), Buffer.from(check, "hex"));
  } catch {
    return false;
  }
}

function b64url(buf) {
  return Buffer.from(buf).toString("base64url");
}
function signToken(payload) {
  const data = b64url(JSON.stringify(payload));
  const sig = crypto.createHmac("sha256", TOKEN_SECRET).update(data).digest("base64url");
  return `${data}.${sig}`;
}
function verifyToken(token) {
  if (!token || !token.includes(".")) return null;
  const [data, sig] = token.split(".");
  const expected = crypto.createHmac("sha256", TOKEN_SECRET).update(data).digest("base64url");
  try {
    if (!crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return null;
  } catch {
    return null;
  }
  try {
    const payload = JSON.parse(Buffer.from(data, "base64url").toString("utf8"));
    if (payload.exp && Date.now() > payload.exp) return null;
    return payload;
  } catch {
    return null;
  }
}

async function getJSON(store, key, fallback) {
  const v = await store.get(key, { type: "json" });
  return v == null ? fallback : v;
}
async function setJSON(store, key, value) {
  await store.setJSON(key, value);
}

async function ensureSeed(store) {
  const seeded = await store.get("meta:seeded");
  if (seeded) return;
  const books = [
    {
      id: 1,
      slug: "frankenstein",
      title: "Frankenstein; Or, The Modern Prometheus",
      authors: "Mary Wollstonecraft Shelley",
      description: "A classic of Gothic literature (public domain).",
      language: "en",
      subjects: ["Gothic", "Classics", "Science Fiction"],
      license: "public_domain",
      cover_url: "",
      source: "seed",
      download_url: "",
      text: "",
      created_at: nowIso(),
    },
    {
      id: 2,
      slug: "pride-and-prejudice",
      title: "Pride and Prejudice",
      authors: "Jane Austen",
      description: "A novel of manners (public domain).",
      language: "en",
      subjects: ["Classics", "Romance"],
      license: "public_domain",
      cover_url: "",
      source: "seed",
      download_url: "",
      text: "",
      created_at: nowIso(),
    },
    {
      id: 3,
      slug: "the-republic",
      title: "The Republic",
      authors: "Plato",
      description: "Socratic dialogue on justice (public domain).",
      language: "en",
      subjects: ["Philosophy", "Classics"],
      license: "public_domain",
      cover_url: "",
      source: "seed",
      download_url: "",
      text: "",
      created_at: nowIso(),
    },
  ];
  const bundles = [
    {
      id: 1,
      slug: "classic-starters",
      title: "Classic Starters",
      description: "A small starter bundle of public-domain classics.",
      price_cents: 0,
      currency: "USD",
      book_ids: [1, 2, 3],
      cover_url: "",
      active: true,
      created_at: nowIso(),
    },
  ];
  await setJSON(store, "meta:books", books);
  await setJSON(store, "meta:bundles", bundles);
  await setJSON(store, "meta:users", []);
  await setJSON(store, "meta:seq", { book: 3, bundle: 1, user: 0 });
  await store.set("meta:seeded", "1");
}

async function getUserFromReq(req, store) {
  const h = req.headers.get("authorization") || "";
  const m = h.match(/^Bearer\s+(.+)$/i);
  if (!m) return null;
  const payload = verifyToken(m[1]);
  if (!payload || !payload.sub) return null;
  const users = await getJSON(store, "meta:users", []);
  return users.find((u) => u.id === payload.sub) || null;
}

function userPayload(u) {
  return {
    id: u.id,
    email: u.email,
    name: u.name || null,
    is_admin: !!u.is_admin,
    created_at: u.created_at,
  };
}

function parseBody(req) {
  return req.json().catch(() => ({}));
}

function routePath(url) {
  // supports /.netlify/functions/api/<splat> and /api/v1/<splat>
  const p = url.pathname;
  let rest = p;
  rest = rest.replace(/^\/\.netlify\/functions\/api\/?/, "");
  rest = rest.replace(/^\/api\/v1\/?/, "");
  return rest.replace(/^\/+/, "").replace(/\/+$/, "");
}

function paginate(items, url) {
  const page = Math.max(1, parseInt(url.searchParams.get("page") || "1", 10) || 1);
  const pageSize = Math.min(
    100,
    Math.max(1, parseInt(url.searchParams.get("page_size") || url.searchParams.get("limit") || "20", 10) || 20),
  );
  const total = items.length;
  const start = (page - 1) * pageSize;
  const slice = items.slice(start, start + pageSize);
  return { items: slice, total, page, page_size: pageSize, pages: Math.max(1, Math.ceil(total / pageSize)) };
}

export default async (req, context) => {
  try {
    const store = getStore({ name: STORE, consistency: "strong" });
    await ensureSeed(store);
    const url = new URL(req.url);
    const path = routePath(url);
    const method = req.method.toUpperCase();

    // --- Health / config (no third-party deps) ---
    if (path === "health" || path === "") {
      return json(200, { status: "ok", service: "babes-bookstore", runtime: "netlify-functions" });
    }
    if (path === "checkout/config") {
      return json(200, {
        providers: [],
        payments_enabled: false,
        mode: "free",
        message: "Payments disabled (zero-dependency Netlify mode).",
      });
    }
    if (path === "config" || path === "site/config") {
      return json(200, { payments_enabled: false, providers: [] });
    }

    // --- Auth (local, no Google/SendGrid) ---
    if (path === "auth/register" && method === "POST") {
      const body = await parseBody(req);
      const email = normEmail(body.email);
      const password = String(body.password || "");
      const name = body.name ? String(body.name) : null;
      if (!email || !email.includes("@") || password.length < 8) {
        return json(422, { detail: "Valid email and password (min 8 chars) required." });
      }
      const users = await getJSON(store, "meta:users", []);
      if (users.find((u) => normEmail(u.email) === email)) {
        return json(400, { detail: "Email already registered." });
      }
      const seq = await getJSON(store, "meta:seq", { user: 0 });
      seq.user = (seq.user || 0) + 1;
      // Bootstrap: first user becomes admin; or allow via ADMIN_EMAILS env.
      const bootstrapAdmin = users.length === 0 || ADMIN_EMAILS.includes(email);
      const user = {
        id: `u${seq.user}`,
        email,
        name,
        password_hash: hashPassword(password),
        is_admin: bootstrapAdmin,
        created_at: nowIso(),
      };
      users.push(user);
      await setJSON(store, "meta:users", users);
      await setJSON(store, "meta:seq", seq);
      const token = signToken({ sub: user.id, exp: Date.now() + 1000 * 60 * 60 * 24 * 30 });
      return json(200, { access_token: token, token_type: "bearer", user: userPayload(user) });
    }
    if (path === "auth/login" && method === "POST") {
      const body = await parseBody(req);
      const email = normEmail(body.email);
      const password = String(body.password || "");
      const users = await getJSON(store, "meta:users", []);
      const user = users.find((u) => normEmail(u.email) === email);
      if (!user || !verifyPassword(password, user.password_hash)) {
        return json(401, { detail: "Invalid email or password." });
      }
      // Re-evaluate admin (env + bootstrap safety: if no other admins, keep/grant carefully)
      const anyAdmin = users.some((u) => u.is_admin);
      user.is_admin = !!user.is_admin || ADMIN_EMAILS.includes(email) || !anyAdmin;
      await setJSON(store, "meta:users", users);
      const token = signToken({ sub: user.id, exp: Date.now() + 1000 * 60 * 60 * 24 * 30 });
      return json(200, { access_token: token, token_type: "bearer", user: userPayload(user) });
    }
    if (path === "auth/me" && method === "GET") {
      const user = await getUserFromReq(req, store);
      if (!user) return json(401, { detail: "Not authenticated." });
      return json(200, userPayload(user));
    }
    if (path.startsWith("auth/google") || path.startsWith("auth/forgot") || path.startsWith("auth/reset")) {
      return json(404, { detail: "This auth method is disabled in Netlify-only mode." });
    }

    // --- Books (NoSQL/Blobs catalog) ---
    const books = await getJSON(store, "meta:books", []);
    if (path === "books" && method === "GET") {
      const q = (url.searchParams.get("q") || url.searchParams.get("search") || "").toLowerCase().trim();
      let items = books;
      if (q) {
        items = books.filter((b) =>
          [b.title, b.authors, b.description, ...(b.subjects || [])].join(" ").toLowerCase().includes(q),
        );
      }
      const p = paginate(items, url);
      return json(200, { ...p, books: p.items, results: p.items, data: p.items });
    }
    const bookDownload = path.match(/^books\/(.+)\/download$/);
    if (bookDownload && method === "GET") {
      const key = decodeURIComponent(bookDownload[1]);
      const b = books.find((x) => String(x.id) === key || x.slug === key);
      if (!b) return json(404, { detail: "Book not found." });
      if (b.download_url) return Response.redirect(b.download_url, 302);
      const body = `# ${b.title}\n\nBy ${b.authors || "Unknown"}\n\n${b.description || ""}\n\n(Full file storage can be provided via Netlify Blobs in this Netlify-only deployment.)\n`;
      return new Response(body, { status: 200, headers: { "content-type": "text/plain; charset=utf-8", "content-disposition": `attachment; filename="${(b.slug||b.id)}.txt"` } });
    }
    const bookMatch = path.match(/^books\/(.+)$/);
    if (bookMatch && method === "GET") {
      const key = decodeURIComponent(bookMatch[1]);
      const b = books.find((x) => String(x.id) === key || x.slug === key);
      if (!b) return json(404, { detail: "Book not found." });
      return json(200, b);
    }
    if ((path === "search" || path === "books/search") && method === "GET") {
      const q = (url.searchParams.get("q") || "").toLowerCase().trim();
      const items = q
        ? books.filter((b) => [b.title, b.authors, b.description].join(" ").toLowerCase().includes(q))
        : books;
      return json(200, paginate(items, url));
    }

    // --- Bundles ---
    const bundles = await getJSON(store, "meta:bundles", []);
    if (path === "bundles" && method === "GET") {
      const active = bundles.filter((b) => b.active !== false);
      const p = paginate(active, url);
      return json(200, { ...p, bundles: p.items, results: p.items, data: p.items });
    }
    const bundleMatch = path.match(/^bundles\/(.+)$/);
    if (bundleMatch && method === "GET") {
      const key = decodeURIComponent(bundleMatch[1]);
      const b = bundles.find((x) => String(x.id) === key || x.slug === key);
      if (!b) return json(404, { detail: "Bundle not found." });
      const bundleBooks = (b.book_ids || []).map((id) => books.find((x) => x.id === id)).filter(Boolean);
      return json(200, { ...b, books: bundleBooks });
    }

    // --- Library / wishlist / purchases / free claim (Netlify Blobs, no payments) ---
    const user = await getUserFromReq(req, store);
    if (path === "checkout/free" && method === "POST") {
      if (!user) return json(401, { detail: "Not authenticated." });
      const body = await parseBody(req);
      const slug = body.bundle_slug || body.bundle_id;
      const bundles = await getJSON(store, "meta:bundles", []);
      const books = await getJSON(store, "meta:books", []);
      const b = bundles.find((x) => String(x.id) === String(slug) || x.slug === slug);
      if (!b) return json(404, { detail: "Bundle not found." });
      const lib = await getJSON(store, `user:${user.id}:library`, { items: [], wishlist: [], progress: {}, bundles: [] });
      lib.bundles = lib.bundles || [];
      if (!lib.bundles.find((x) => x === b.id)) lib.bundles.push(b.id);
      for (const bid of b.book_ids || []) {
        if (!lib.items.find((i) => i.book_id === bid)) lib.items.push({ book_id: bid, added_at: nowIso(), bundle_id: b.id });
      }
      await setJSON(store, `user:${user.id}:library`, lib);
      return json(200, { ok: true, message: "Bundle added to your library.", checkout_url: "/account" });
    }
    if (path.startsWith("checkout/") && method === "POST") {
      return json(400, { detail: "Payments are disabled in Netlify-only mode." });
    }
    if (path.startsWith("library") || path.startsWith("wishlist") || path.startsWith("purchases") || path === "me/library") {
      if (!user) return json(401, { detail: "Not authenticated." });
      const lib = await getJSON(store, `user:${user.id}:library`, { items: [], wishlist: [], progress: {} });
      if (method === "GET") return json(200, lib);
      if (method === "POST") {
        const body = await parseBody(req);
        // generic upsert helpers
        if (path.includes("wishlist") && body.book_id) {
          if (!lib.wishlist.includes(body.book_id)) lib.wishlist.push(body.book_id);
        } else if (body.book_id) {
          if (!lib.items.find((i) => i.book_id === body.book_id)) lib.items.push({ book_id: body.book_id, added_at: nowIso() });
        }
        await setJSON(store, `user:${user.id}:library`, lib);
        return json(200, lib);
      }
      if (method === "DELETE") return json(200, { ok: true });
      return json(200, lib);
    }

    // --- Admin (Netlify-only; replaces Fly/Grafana ops with function/Blobs-backed stats) ---
    if (path.startsWith("admin")) {
      if (!user) return json(401, { detail: "Not authenticated." });
      if (!user.is_admin) return json(403, { detail: "Admin access required." });
      const users = await getJSON(store, "meta:users", []);
      if (path === "admin/stats" || path === "admin/dashboard") {
        const total = books.length;
        return json(200, {
          books: { total, approved: total, pending: 0, rejected: 0 },
          purchases: { total: 0, revenue_cents: 0 },
          bundles: { total: bundles.length },
          users: { total: users.length },
          mode: "netlify-only",
          observability: "Use Netlify function logs/analytics (Grafana replaced by platform logs in Netlify-only mode).",
        });
      }
      if (path === "admin/books" || path.startsWith("admin/books")) {
        if (method === "GET") return json(200, { items: books, total: books.length, ...paginate(books, url) });
        if (method === "POST" && (path === "admin/books" || path === "admin/books/import")) {
          const body = await parseBody(req);
          const incoming = Array.isArray(body) ? body : (Array.isArray(body.books) ? body.books : []);
          if (!incoming.length) return json(400, { detail: "No books provided. Send { books: [...] } or [...]." });
          const seq = await getJSON(store, "meta:seq", { book: 0, bundle: 0, user: 0 });
          let nextId = (seq.book || 0) + 1;
          const existingIds = new Set(books.map((b) => b.id));
          let added = 0;
          for (const b of incoming) {
            const id = b.id != null && !existingIds.has(b.id) ? b.id : nextId++;
            if (existingIds.has(id)) continue;
            existingIds.add(id);
            books.push({
              id,
              title: b.title || "Untitled",
              authors: b.author || b.authors || "",
              author: b.author || b.authors || "",
              description: b.description || "",
              source: b.source || "imported",
              source_id: b.source_id || "",
              source_url: b.source_url || "",
              license_type: b.license_type || b.license || "public_domain",
              license: b.license_type || b.license || "public_domain",
              license_url: b.license_url || "",
              category: b.category || "",
              tags: b.tags || [],
              language: b.language || "en",
              page_count: b.page_count || null,
              publication_year: b.publication_year || null,
              cover_url: b.cover_url || "",
              download_url: b.download_url || "",
              status: b.status || "approved",
              asset_verified: !!b.asset_verified,
              slug: b.slug || String(b.title || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
              subjects: b.subjects || b.tags || [],
              text: b.text || "",
              created_at: b.created_at || nowIso(),
            });
            added++;
          }
          seq.book = Math.max(seq.book || 0, nextId - 1);
          await setJSON(store, "meta:books", books);
          await setJSON(store, "meta:seq", seq);
          return json(200, { ok: true, imported: added, total: books.length, message: `Imported ${added} books. Total: ${books.length}.` });
        }
        return json(200, { ok: true, message: "Book management is limited in Netlify-only mode." });
      }
      if (path === "admin/bundles" || path.startsWith("admin/bundles")) {
        if (method === "GET") return json(200, { items: bundles, total: bundles.length, ...paginate(bundles, url) });
        return json(200, { ok: true });
      }
      if (path === "admin/purchases" || path.startsWith("admin/purchases")) {
        if (method === "GET") return json(200, { items: [], total: 0 });
        return json(200, { ok: true });
      }
      if (method === "GET") return json(200, { items: [], total: 0, message: "Admin feature limited in Netlify-only mode." });
      return json(200, { ok: true, message: "Background jobs/scraping disabled in Netlify-only mode." });
    }

    // --- Supporting endpoints: stubs with compatible shapes ---
    if (path.startsWith("authors")) return json(200, method === "GET" && !path.includes("/") ? paginate([], url) : { items: [], total: 0 });
    if (path.startsWith("categories")) return json(200, { items: [], total: 0 });
    if (path.startsWith("censorship") || path.startsWith("banned")) return json(200, { items: [], total: 0 });
    if (path.startsWith("reviews")) return json(200, method === "GET" ? { items: [], total: 0 } : { ok: true });
    if (path.startsWith("themes")) return json(200, { theme: null, items: [] });
    if (path === "home/feed" || path.startsWith("home")) return json(200, { rows: [] });
    if (path.startsWith("webhooks")) return json(200, { ok: true, ignored: true });

    return json(404, { detail: `Not found: ${path}` });
  } catch (err) {
    console.error(err);
    return json(500, { detail: "Internal error", message: String(err && err.message ? err.message : err) });
  }
};

export const config = {
  path: ["/api/v1/*", "/.netlify/functions/api/*"],
};
