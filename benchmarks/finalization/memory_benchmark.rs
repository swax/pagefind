//! Synthetic input only; no application data or credentials are used.
use anyhow::{bail, Result};
use pagefind::{api::PagefindIndex, options::PagefindServiceConfig};
use sha1::{Digest, Sha1};
use std::{collections::BTreeMap, fmt::Write, time::Instant};

fn token(mut n: usize) -> String {
    let mut result = String::from("term");
    for _ in 0..4 {
        result.push((b'a' + (n % 26) as u8) as char);
        n /= 26;
    }
    result
}

fn high_water_kib() -> Option<u64> {
    std::fs::read_to_string("/proc/self/status").ok()?.lines()
        .find_map(|line| line.strip_prefix("VmHWM:")?.split_whitespace().next()?.parse().ok())
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let records: usize = args.get(1).map(String::as_str).unwrap_or("16000").parse()?;
    let words: usize = args.get(2).map(String::as_str).unwrap_or("512").parse()?;
    let mode = args.get(3).map(String::as_str).unwrap_or("retain");
    let language_count: usize = args.get(4).map(String::as_str).unwrap_or("1").parse()?;
    if ![1, 3].contains(&language_count) { bail!("Expected one or three languages"); }
    let options = PagefindServiceConfig::builder().keep_index_url(true).build();
    let mut index = PagefindIndex::new(Some(options))?;
    let vocabulary: Vec<_> = (0..32768).map(token).collect();
    let started = Instant::now();
    let mut input_bytes = 0;
    for n in 0..records {
        let language = ["en", "fr", "de"][n % language_count];
        let mut text = String::with_capacity(words * 10);
        for offset in 0..words {
            write!(text, "{} ", vocabulary[(n * 73 + offset * 31) % vocabulary.len()])?;
        }
        text.push_str("café cafes naïve résumé customers coffee pastries");
        if n % 5 == 0 {
            input_bytes += text.len();
            index.add_custom_record(format!("/records/{n}"), text, language.into(),
                Some(BTreeMap::from([("title".into(), format!("Record {n}"))])),
                Some(BTreeMap::from([("category".into(), vec![format!("group{}", n % 8)])])),
                Some(BTreeMap::from([("ordinal".into(), n.to_string())]))).await?;
        } else {
            let html = format!("<html lang=\"{language}\"><body><main data-pagefind-body>\
                <h1 data-pagefind-meta=\"title\" data-pagefind-weight=\"2\">Article {n}</h1>\
                <span data-pagefind-filter=\"category\">group{}</span>\
                <span data-pagefind-sort=\"ordinal\">{n}</span>\
                <h2 id=\"section\">Café section</h2><p>{text}</p>\
                <aside data-pagefind-ignore>Excluded private-looking synthetic text</aside>\
                </main></body></html>", n % 8);
            input_bytes += html.len();
            index.add_html_file(None, Some(format!("/articles/{n}")), html).await?;
        }
    }
    let ingest_seconds = started.elapsed().as_secs_f64();
    let ingest_peak_kib = high_water_kib();
    let finalizing = Instant::now();
    let mut files = match mode {
        "retain" => index.get_files().await?,
        #[cfg(feature = "consuming_benchmark")]
        "consume" => index.into_files().await?,
        _ => bail!("Unsupported finalization mode"),
    };
    let finalize_seconds = finalizing.elapsed().as_secs_f64();
    let finalize_peak_kib = high_water_kib();
    files.sort_by(|a, b| a.filename.cmp(&b.filename));
    let mut total_bytes = 0;
    let mut digest = Sha1::new();
    let mut manifest = BTreeMap::new();
    for file in &files {
        total_bytes += file.contents.len();
        let hash = format!("{:x}", Sha1::digest(&file.contents));
        let path = file.filename.to_string_lossy().into_owned();
        digest.update(path.as_bytes()); digest.update([0]); digest.update(hash.as_bytes());
        manifest.insert(path, hash);
    }
    if let Some(path) = args.get(5) {
        std::fs::write(path, serde_json::to_vec_pretty(&manifest)?)?;
    }
    println!("BENCHMARK {}", serde_json::json!({
        "records":records,"words_per_record":words,"languages":language_count,
        "mode":mode,"input_bytes":input_bytes,"ingest_seconds":ingest_seconds,
        "finalize_seconds":finalize_seconds,"ingest_peak_kib":ingest_peak_kib,
        "finalize_peak_kib":finalize_peak_kib,"files":files.len(),"output_bytes":total_bytes,
        "bundle_sha1":format!("{:x}",digest.finalize())
    }));
    Ok(())
}
