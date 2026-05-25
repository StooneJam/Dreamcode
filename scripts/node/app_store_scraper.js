/**
 * App Store scraper — stdout JSON output, called from Python via subprocess.
 *
 * Usage:
 *   node app_store_scraper.js <product_name> [country] [max_reviews]
 *
 * Output (JSON):
 *   { "product_name": "...", "country": "cn", "rating": 4.5,
 *     "review_count": 1234, "reviews": ["...", ...] }
 */
"use strict";

const store = require("app-store-scraper");

const [, , productName, country = "cn", maxReviews = "50"] = process.argv;

if (!productName) {
  process.stderr.write("Usage: node app_store_scraper.js <product_name> [country] [max_reviews]\n");
  process.exit(1);
}

const nReviews = Math.min(parseInt(maxReviews, 10) || 50, 200);

async function run() {
  // Search for the app by name
  const results = await store.search({ term: productName, country, num: 5, lang: "zh" });

  if (!results || results.length === 0) {
    const out = { product_name: productName, country, rating: null, review_count: null, reviews: [], error: "app_not_found" };
    process.stdout.write(JSON.stringify(out, null, 2));
    return;
  }

  // Pick the best match: exact name match first, otherwise first result
  const lower = productName.toLowerCase();
  const app = results.find(r => r.title.toLowerCase().includes(lower)) || results[0];

  // Fetch reviews (page 1-3 to get enough samples)
  const pages = nReviews > 100 ? [1, 2, 3] : nReviews > 50 ? [1, 2] : [1];
  const reviewPromises = pages.map(page =>
    store.reviews({ id: app.id, country, sort: store.sort.RECENT, page }).catch(() => [])
  );
  const reviewPages = await Promise.all(reviewPromises);
  const rawReviews = reviewPages.flat().slice(0, nReviews);

  const output = {
    product_name: productName,
    app_title: app.title,
    app_id: app.id,
    country,
    rating: app.score ?? null,
    review_count: app.reviews ?? null,
    reviews: rawReviews.map(r => ({
      id: r.id,
      rating: r.score,
      title: r.title,
      text: r.text,
      date: r.updated,
    })),
  };

  process.stdout.write(JSON.stringify(output, null, 2));
}

run().catch(err => {
  const out = { product_name: productName, country, rating: null, review_count: null, reviews: [], error: err.message };
  process.stdout.write(JSON.stringify(out, null, 2));
  process.exit(0); // non-fatal — Python side handles missing data
});
