from core.errors import AppValidationError
from core.url_input import build_url_attempts


def assert_error_message(raw_url: str, expected_substring: str) -> None:
    try:
        build_url_attempts(raw_url)
    except AppValidationError as exc:
        assert expected_substring in exc.message
        return
    raise AssertionError(f"Expected AppValidationError for input: {raw_url}")


# Valid explicit URL should pass unchanged.
attempts, display, has_scheme = build_url_attempts("https://eurovisionworld.com/")
assert attempts == ["https://eurovisionworld.com/"]
assert display == "https://eurovisionworld.com/"
assert has_scheme is True

# Scheme-less input should try HTTPS first, then HTTP.
attempts, display, has_scheme = build_url_attempts("example.com")
assert attempts == ["https://example.com", "http://example.com"]
assert display == "example.com"
assert has_scheme is False

# Common scheme typos should provide a suggestion.
assert_error_message("htts://example.com", "Did you mean: https://example.com ?")
assert_error_message("htp://example.com", "Did you mean: http://example.com ?")
assert_error_message("https:/example.com", "Did you mean: https://example.com ?")
assert_error_message("https//example.com", "Did you mean: https://example.com ?")

# Unsupported schemes should be rejected with a clear message.
assert_error_message("ftp://example.com", "Only http:// and https:// URLs are supported.")

print("URL input handling checks passed.")
