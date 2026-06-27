import httpx
from scada_core.client import SyncScadaClient


def test_sync_list_tags():
    def handler(req):
        return httpx.Response(200, json=[{"id": 1, "name": "PT-101"}])

    c = SyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))
    r = c.list_tags()
    assert r.ok and r.data[0]["name"] == "PT-101"
    c.close()


def test_sync_legacy_output_on_error():
    def handler(req):
        return httpx.Response(404, json={"detail": "no"})

    c = SyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))
    r = c.list_plcs()
    assert r.legacy() == {"error": True, "status": 404, "detail": {"detail": "no"}}
    c.close()


def test_sync_client_reuses_one_event_loop_for_multiple_calls():
    seen = []

    def handler(req):
        seen.append(req.url.path)
        if req.url.path == "/ready":
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(200, json={"status": "ok"})

    c = SyncScadaClient(base_url="http://t", transport=httpx.MockTransport(handler))
    assert c.health().ok
    assert c.ready().ok
    c.close()

    assert seen == ["/health", "/ready"]
