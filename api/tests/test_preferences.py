import pytest


@pytest.fixture
def signed_in(api, make_user):
    make_user("p@example.com")
    api.login("p@example.com")
    return api


def test_defaults(signed_in):
    p = signed_in.get("/api/me/preferences").json()
    assert p == {
        "currency": "NGN",
        "timezone": "Africa/Lagos",
        "week_start": 1,
        "budget_alert_thresholds": [70, 90, 100],
        "notify_in_app": True,
        "notify_email": False,
        "ai_enabled": False,
        "external_ai_consent": False,
    }


def test_update_and_persist(signed_in):
    r = signed_in.patch(
        "/api/me/preferences",
        {"timezone": "Europe/London", "budget_alert_thresholds": [100, 50], "notify_email": True},
    )
    assert r.status_code == 200
    p = signed_in.get("/api/me/preferences").json()
    assert p["timezone"] == "Europe/London"
    assert p["budget_alert_thresholds"] == [50, 100]
    assert p["notify_email"] is True


@pytest.mark.parametrize(
    "patch",
    [
        {"timezone": "Mars/Olympus"},
        {"currency": "XYZ"},
        {"currency": "USD"},  # not yet enabled in the currencies table
        {"week_start": 9},
        {"budget_alert_thresholds": []},
        {"budget_alert_thresholds": [0]},
        {"budget_alert_thresholds": [70, 70]},
    ],
)
def test_invalid_values_rejected(signed_in, patch):
    assert signed_in.patch("/api/me/preferences", patch).status_code == 422


def test_external_ai_consent_is_audited(signed_in):
    from tests.conftest import db_scalar

    signed_in.patch("/api/me/preferences", {"external_ai_consent": True})
    assert db_scalar("SELECT count(*) FROM audit_events WHERE action='consent.external_ai'") == 1
