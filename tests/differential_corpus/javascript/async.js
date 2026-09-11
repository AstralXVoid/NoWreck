// Async: async functions, promises, async methods.

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`bad status ${response.status}`);
  }
  return response.json();
}

async function fetchAll(urls) {
  const promises = urls.map((url) => fetchJson(url));
  return Promise.all(promises);
}

class ApiClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async get(path) {
    return fetchJson(`${this.baseUrl}${path}`);
  }

  async batch(paths) {
    const results = [];
    for (const path of paths) {
      results.push(await this.get(path));
    }
    return results;
  }
}