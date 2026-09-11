// Async: async fns (same node type as sync — captured).

async fn fetch_page(url: &str) -> Result<String, String> {
    if url.is_empty() {
        return Err("empty url".to_string());
    }
    Ok(format!("<html>{url}</html>"))
}

async fn fetch_many(urls: &[&str]) -> Result<Vec<String>, String> {
    let mut results = Vec::new();
    for url in urls {
        let page = fetch_page(url).await?;
        results.push(page);
    }
    Ok(results)
}

pub async fn run(urls: &[&str]) -> Result<usize, String> {
    let pages = fetch_many(urls).await?;
    Ok(pages.len())
}

struct Downloader {
    concurrency: usize,
}

impl Downloader {
    async fn download(&self, urls: &[&str]) -> Result<usize, String> {
        let pages = fetch_many(urls).await?;
        Ok(pages.len() + self.concurrency)
    }
}