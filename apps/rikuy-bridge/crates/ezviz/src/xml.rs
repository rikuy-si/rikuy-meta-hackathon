//! A tiny namespace-agnostic XML tree for SOAP responses.
//!
//! ONVIF devices disagree on namespace prefixes (`tt:`, `ns2:`, none), so the
//! tree keeps only local names; lookups never depend on a prefix.
use quick_xml::events::Event;
use quick_xml::Reader;

#[derive(Debug, Clone, Default)]
pub struct Element {
    pub name: String,
    pub attrs: Vec<(String, String)>,
    pub children: Vec<Element>,
    pub text: String,
}

impl Element {
    pub fn child(&self, name: &str) -> Option<&Element> {
        self.children.iter().find(|c| c.name == name)
    }

    pub fn children_named<'a>(&'a self, name: &'a str) -> impl Iterator<Item = &'a Element> + 'a {
        self.children.iter().filter(move |c| c.name == name)
    }

    /// Follow direct children by local name.
    pub fn path(&self, path: &[&str]) -> Option<&Element> {
        let mut cur = self;
        for p in path {
            cur = cur.child(p)?;
        }
        Some(cur)
    }

    /// First descendant (depth-first, self excluded) with this local name.
    pub fn find(&self, name: &str) -> Option<&Element> {
        for c in &self.children {
            if c.name == name {
                return Some(c);
            }
            if let Some(f) = c.find(name) {
                return Some(f);
            }
        }
        None
    }

    /// Every descendant with this local name, in document order.
    pub fn find_all<'a>(&'a self, name: &str, out: &mut Vec<&'a Element>) {
        for c in &self.children {
            if c.name == name {
                out.push(c);
            }
            c.find_all(name, out);
        }
    }

    pub fn attr(&self, name: &str) -> Option<&str> {
        self.attrs.iter().find(|(k, _)| k == name).map(|(_, v)| v.as_str())
    }

    pub fn trimmed(&self) -> &str {
        self.text.trim()
    }

    /// Trimmed text of the first descendant with this name.
    pub fn text_of(&self, name: &str) -> Option<&str> {
        self.find(name).map(|e| e.trimmed()).filter(|s| !s.is_empty())
    }
}

fn local(name: &[u8]) -> String {
    let s = String::from_utf8_lossy(name);
    match s.rsplit_once(':') {
        Some((_, l)) => l.to_string(),
        None => s.to_string(),
    }
}

pub fn parse(s: &str) -> Result<Element, String> {
    let mut reader = Reader::from_str(s);
    reader.config_mut().trim_text(false);
    let mut stack: Vec<Element> = vec![Element { name: "#document".into(), ..Default::default() }];
    loop {
        match reader.read_event().map_err(|e| format!("xml: {e}"))? {
            Event::Start(e) => {
                stack.push(element_from(&e)?);
            }
            Event::Empty(e) => {
                let el = element_from(&e)?;
                stack.last_mut().expect("document root").children.push(el);
            }
            Event::End(_) => {
                if stack.len() < 2 {
                    return Err("xml: unbalanced end tag".into());
                }
                let el = stack.pop().unwrap();
                stack.last_mut().unwrap().children.push(el);
            }
            Event::Text(t) => {
                let txt = t.unescape().map_err(|e| format!("xml text: {e}"))?;
                stack.last_mut().unwrap().text.push_str(&txt);
            }
            Event::CData(t) => {
                stack.last_mut().unwrap().text.push_str(&String::from_utf8_lossy(&t));
            }
            Event::Eof => break,
            _ => {}
        }
    }
    if stack.len() != 1 {
        return Err("xml: unterminated element".into());
    }
    let mut doc = stack.pop().unwrap();
    match doc.children.len() {
        0 => Err("xml: empty document".into()),
        _ => Ok(doc.children.remove(0)),
    }
}

fn element_from(e: &quick_xml::events::BytesStart<'_>) -> Result<Element, String> {
    let mut attrs = Vec::new();
    for a in e.attributes() {
        let a = a.map_err(|e| format!("xml attr: {e}"))?;
        let v = a.unescape_value().map_err(|e| format!("xml attr: {e}"))?;
        attrs.push((local(a.key.as_ref()), v.to_string()));
    }
    Ok(Element { name: local(e.name().as_ref()), attrs, children: vec![], text: String::new() })
}

/// Escape text for an XML element or attribute value.
pub fn escape(s: &str) -> String {
    let mut o = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => o.push_str("&amp;"),
            '<' => o.push_str("&lt;"),
            '>' => o.push_str("&gt;"),
            '"' => o.push_str("&quot;"),
            '\'' => o.push_str("&apos;"),
            _ => o.push(c),
        }
    }
    o
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn local_names_ignore_prefixes() {
        let x = r#"<s:Envelope xmlns:s="a"><s:Body><tds:GetServicesResponse>
            <tds:Service><tds:Namespace>http://www.onvif.org/ver20/media/wsdl</tds:Namespace>
            <tds:XAddr>http://1.2.3.4/onvif/media</tds:XAddr></tds:Service>
            <Service><Namespace>ns-b</Namespace><XAddr>x &amp; y</XAddr></Service>
            <tt:Empty tok="1"/></tds:GetServicesResponse></s:Body></s:Envelope>"#;
        let e = parse(x).unwrap();
        assert_eq!(e.name, "Envelope");
        let r = e.path(&["Body", "GetServicesResponse"]).unwrap();
        let svcs: Vec<_> = r.children_named("Service").collect();
        assert_eq!(svcs.len(), 2);
        assert_eq!(svcs[1].text_of("XAddr"), Some("x & y"));
        assert_eq!(r.find("Empty").unwrap().attr("tok"), Some("1"));
    }

    #[test]
    fn escape_roundtrip() {
        assert_eq!(escape(r#"a<b>&"c'"#), "a&lt;b&gt;&amp;&quot;c&apos;");
    }
}
