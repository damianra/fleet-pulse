"""Fixtures pytest FleetPulse — TestClient + sqlite de prueba.
DATABASE_URL/JWT_SECRET/RATE_LIMIT_MAX se pisan ANTES de importar la
app (el engine y la config se arman al importar); init_db() corre en
fixture porque el lifespan solo dispara dentro de `with TestClient`.
`admin` = primer usuario registrado (bootstrap → rol admin) con
cookies + header x-csrf-token ya configurados."""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test_fleetpulse.db')
os.environ.setdefault('RATE_LIMIT_MAX', '500')
os.environ.setdefault('JWT_SECRET', 'test-only-fleetpulse-secret-key-32b!')
os.environ.setdefault('ALERTS_INTERVAL_S', '3600')

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

TEST_DB = 'test_fleetpulse.db'


@pytest.fixture(scope='session')
def client():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    yield TestClient(app)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(scope='session')
def admin(client):
    r = client.post('/api/auth/register', json={
        'email': 'admin@fleetpulse.test', 'password': 'adminpass123',
        'full_name': 'Admin Test'})
    assert r.status_code == 201 and r.json()['role'] == 'admin'
    client.headers['x-csrf-token'] = client.cookies.get('csrf')
    return client


@pytest.fixture()
def anon():
    return TestClient(app)
