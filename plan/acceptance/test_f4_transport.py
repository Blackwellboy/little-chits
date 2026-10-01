import json


def test_bounded_sequenced_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    q = rt.new_client_queue()
    assert q.maxsize == 256
    for i in range(1000):
        rt.push(q, {"type": "frame", "i": i})
    assert q.qsize() <= 256
    msgs = [json.loads(q.get_nowait()) for _ in range(q.qsize())]
    assert all("seq" in m and m["gen"] == rt.gen for m in msgs)
    seqs = [m["seq"] for m in msgs]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs)))  # no gaps inside what the client gets
    hellos = [m for m in msgs if m["type"] == "hello"]
    assert hellos and hellos[0].get("resync") is True and hellos[0]["seq"] == 1
    g = rt.gen
    rt.reset(seed=9)
    assert rt.gen == g + 1
