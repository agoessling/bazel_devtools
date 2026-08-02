use greeting::greeting;

#[test]
fn says_hello() {
    assert_eq!(greeting("Bazel"), "Hello, Bazel!");
}
