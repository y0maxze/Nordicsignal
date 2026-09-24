"""A successful login page must not masquerade as successful application QA."""
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    'production_boundary', Path(__file__).parents[1] / 'scripts/verify_production.py')
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


def test_requires_exact_access_tenant_and_login_path():
    location = 'https://lucky-darkness-5204.cloudflareaccess.com/cdn-cgi/access/login/app'
    assert verification.is_access_login(302, {'Location': location})
    assert not verification.is_access_login(200, {'Location': location})
    assert not verification.is_access_login(302, {'Location': location.replace('.com/', '.com.evil.test/')})
    assert not verification.is_access_login(302, {'Location': location.replace('/cdn-cgi/access/login/app', '/error')})


def test_public_backend_fails_verification(monkeypatch):
    def fetch(origin, path):
        if origin == verification.FRONTEND:
            return 302, {'Location': 'https://lucky-darkness-5204.cloudflareaccess.com/cdn-cgi/access/login/app'}
        return 200, {}
    monkeypatch.setattr(verification, 'fetch_boundary', fetch)
    monkeypatch.setattr(verification, 'checks', [])
    verification.run()
    failed = [x for x in verification.checks if not x['passed']]
    assert len(failed) == 7
    assert all(x['check'].startswith('Backend ') for x in failed)
