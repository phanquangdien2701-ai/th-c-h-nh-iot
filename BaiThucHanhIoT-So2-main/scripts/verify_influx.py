# scripts/verify_influx.py — chẩn đoán kết nối InfluxDB Cloud
import yaml
from influxdb_client import InfluxDBClient

c = yaml.safe_load(open('config/config.yaml', encoding='utf-8'))['influx']
print('url  :', c['url'])
print('org  :', repr(c['org']))
print('token: starts', c['token'][:8], '…', 'ends', c['token'][-6:], f'(len={len(c["token"])})')
print('-' * 60)

cli = InfluxDBClient(url=c['url'], token=c['token'], org=c['org'])

print('health :', cli.health().status, '|', cli.health().message)

try:
    orgs = cli.organizations_api().find_organizations()
    print('orgs visible :', [(o.name, o.id) for o in orgs])
except Exception as e:
    print('orgs error:', type(e).__name__, e)

try:
    bs = cli.buckets_api().find_buckets()
    print('buckets raw  :', bs)
    if bs is not None:
        print('buckets names:', [b.name for b in bs.buckets])
except Exception as e:
    print('buckets error:', type(e).__name__, e)