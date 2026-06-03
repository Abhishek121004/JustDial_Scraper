import pytest

from app.services.cipher import decode_phone, is_valid_indian_phone
from app.services.url_builder import build_search_url, skill_to_slug


class TestSkillToSlug:
    @pytest.mark.parametrize(
        "skill,expected",
        [
            ("AC Repair", "ac-repair"),
            ("ac repair", "ac-repair"),
            ("Plumbing", "plumbing"),
            ("Electrician Services", "electrician-services"),
        ],
    )
    def test_skill_to_slug(self, skill, expected):
        assert skill_to_slug(skill) == expected


class TestBuildSearchUrl:
    def test_page_one_url(self):
        url = build_search_url("768028", "AC Repair", page=1)
        assert url == "https://www.justdial.com/768028/ac-repair"

    def test_page_two_url(self):
        url = build_search_url("768028", "AC Repair", page=2)
        assert url == "https://www.justdial.com/768028/ac-repair/page-2"

    def test_multi_word_skill(self):
        url = build_search_url("110001", "Electrician Services", page=3)
        assert url == "https://www.justdial.com/110001/electrician-services/page-3"


class TestCipher:
    def test_decode_example_from_pdf(self):
        # 9876543210 encodes as lkjihgfedc (one cipher char per digit)
        assert decode_phone("lkjihgfedc") == "9876543210"

    def test_decode_empty(self):
        assert decode_phone("") == ""

    def test_decode_mixed_invalid_chars_ignored(self):
        assert decode_phone("lk-ji") == "9876"

    def test_is_valid_indian_phone(self):
        assert is_valid_indian_phone("9876543210") is True
        assert is_valid_indian_phone("987654321") is False
        assert is_valid_indian_phone("abc") is False
        assert is_valid_indian_phone("919876543210") is True
