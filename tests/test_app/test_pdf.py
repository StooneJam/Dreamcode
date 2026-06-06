"""测试 /api/report/pdf 的 owner 隔离：PDF 路径只来自服务端记录，不收客户端文件路径。"""
from __future__ import annotations

from pathlib import Path


def _seed_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "report_飞书_deadbeef.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    return pdf


def test_owner_can_fetch_own_pdf(env, auth, tmp_path) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "# 正文", str(_seed_pdf(tmp_path)))
    resp = client.get("/api/report/pdf?report_id=r1", headers=auth("alice"))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b"%PDF-1.4 fake"


def test_other_owner_gets_404(env, auth, tmp_path) -> None:
    client, db = env
    db.save_report("r1", "alice", "飞书", "# 正文", str(_seed_pdf(tmp_path)))
    resp = client.get("/api/report/pdf?report_id=r1", headers=auth("bob"))
    assert resp.status_code == 404                       # bob 拿不到 alice 的 PDF


def test_unknown_report_id_404(env, auth) -> None:
    client, _ = env
    resp = client.get("/api/report/pdf?report_id=nope", headers=auth("alice"))
    assert resp.status_code == 404


def test_path_param_no_longer_reads_files(env, auth, tmp_path) -> None:
    """旧的 ?path= 任意文件读取入口已移除：report_id 必填，path 不再命中任何文件。"""
    secret = tmp_path / "secret.env"
    secret.write_bytes(b"API_KEY=leak")
    client, _ = env
    resp = client.get(f"/api/report/pdf?path={secret}", headers=auth("alice"))
    assert resp.status_code == 422                       # report_id 缺失
    assert b"leak" not in resp.content
