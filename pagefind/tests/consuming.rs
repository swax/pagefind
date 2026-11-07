//! Single-use Pagefind finalization must retain the reusable API's search data.
use pagefind::{api::PagefindIndex, options::PagefindServiceConfig};
use std::collections::BTreeMap;

async fn fixture() -> PagefindIndex {
    let mut index = PagefindIndex::new(Some(
        PagefindServiceConfig::builder()
            .force_language("en".into())
            .build(),
    ))
    .unwrap();
    for n in 0..8 {
        index
            .add_html_file(
                None,
                Some(format!("/sketches/example-{n}")),
                format!(
                    "<html lang=\"en\"><body><main data-pagefind-body>\
                     <h1 data-pagefind-weight=\"2\" data-pagefind-meta=\"title\">Café {n}</h1>\
                     <p>Customers order coffee, cafés, and fresh pastries.</p>\
                     <span data-pagefind-filter=\"type\" hidden>sketch</span>\
                     <p data-pagefind-ignore>Private excluded passage.</p></main></body></html>"
                ),
            )
            .await
            .unwrap();
    }
    // A page without a custom body is excluded once another page declares one.
    index
        .add_html_file(
            None,
            Some("/excluded".into()),
            "<html><body>Entire excluded page.</body></html>".into(),
        )
        .await
        .unwrap();
    // Force-included entity records must survive the same filtering.
    index
        .add_custom_record(
            "/people/example".into(),
            "A performer serving café customers.".into(),
            "en".into(),
            Some(BTreeMap::from([(
                "title".into(),
                "Example Performer".into(),
            )])),
            Some(BTreeMap::from([("type".into(), vec!["sketch".into()])])),
            None,
        )
        .await
        .unwrap();
    index
}

#[tokio::test]
async fn consuming_finalization_preserves_every_bundle_byte() {
    let retained: BTreeMap<_, _> = fixture()
        .await
        .get_files()
        .await
        .unwrap()
        .into_iter()
        .map(|file| (file.filename, file.contents))
        .collect();
    let consumed: BTreeMap<_, _> = fixture()
        .await
        .into_files()
        .await
        .unwrap()
        .into_iter()
        .map(|file| (file.filename, file.contents))
        .collect();
    assert_eq!(retained, consumed);
    assert!(
        consumed
            .keys()
            .any(|p| p.extension().is_some_and(|e| e == "pf_fragment"))
    );
}

#[tokio::test]
async fn consuming_empty_index_preserves_common_assets() {
    let mut retained = PagefindIndex::new(None).unwrap();
    let consumed = PagefindIndex::new(None).unwrap();
    let paths = |files: Vec<pagefind::api::SyntheticFile>| {
        files
            .into_iter()
            .map(|f| f.filename)
            .collect::<std::collections::BTreeSet<_>>()
    };
    assert_eq!(
        paths(retained.get_files().await.unwrap()),
        paths(consumed.into_files().await.unwrap())
    );
}
