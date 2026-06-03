"""URL construction for JustDial search pages."""

JUSTDIAL_BASE = "https://www.justdial.com"


def skill_to_slug(skill: str) -> str:
    """Convert skill name to URL slug: lowercase, spaces to hyphens."""
    return skill.strip().lower().replace(" ", "-")


def build_search_url(pincode: str, skill: str, page: int = 1) -> str:
    """Build JustDial search URL for a given pincode, skill, and page number."""
    slug = skill_to_slug(skill)
    base = f"{JUSTDIAL_BASE}/{pincode.strip()}/{slug}"
    if page <= 1:
        return base
    return f"{base}/page-{page}"
