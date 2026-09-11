// Async: async functions and async methods with TS types.

interface HttpResponse {
  status: number;
  json(): Promise<unknown>;
}

async function fetchJson(url: string): Promise<unknown> {
  const response = (await fetch(url)) as HttpResponse;
  if (response.status !== 200) {
    throw new Error(`bad status ${response.status}`);
  }
  return response.json();
}

async function fetchAll(urls: string[]): Promise<unknown[]> {
  const promises = urls.map((url) => fetchJson(url));
  return Promise.all(promises);
}

class ApiClient {
  constructor(private baseUrl: string) {}

  async get<T>(path: string): Promise<T> {
    return (await fetchJson(`${this.baseUrl}${path}`)) as T;
  }

  async batch<T>(paths: string[]): Promise<T[]> {
    const results: T[] = [];
    for (const path of paths) {
      results.push(await this.get<T>(path));
    }
    return results;
  }
}