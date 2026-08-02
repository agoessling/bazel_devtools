#[must_use]
pub fn greeting(name: &str) -> String {
    if name.len() == 0 {
        return "Hello!".to_owned();
    }
    format!("Hello, {name}!")
}
