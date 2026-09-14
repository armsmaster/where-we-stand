# Корпоративный центр сертификации

Сюда кладётся цепочка сертификатов, по которой npm и pip проверяют TLS
внутренних зеркал. Нужна, только если сборка падает с ошибкой вида

```
npm error code UNABLE_TO_VERIFY_LEAF_SIGNATURE
npm error request to https://nexus.corp/... failed, reason: unable to verify the first certificate
```

или, для pip, `SSL: CERTIFICATE_VERIFY_FAILED`.

## Что положить

Один файл **`ca.pem`** — все сертификаты цепочки (корневой и промежуточные)
в формате PEM, подряд. Файл игнорируется git и монтируется в сборку только
на время установки пакетов: в слои образа он не попадает.

Отключать проверку вместо этого (`strict-ssl=false`,
`NODE_TLS_REJECT_UNAUTHORIZED=0`, `PIP_TRUSTED_HOST`) не нужно.

## Как получить

На рабочей машине браузер уже доверяет зеркалу — значит нужный ЦС установлен
в хранилище Windows. Node его не видит: у него собственный список ЦС.

**1. Узнать, кем выпущен сертификат зеркала** (Git Bash):

```bash
openssl s_client -connect nexus.corp:443 -servername nexus.corp -showcerts </dev/null 2>/dev/null | grep -E "^ *[0-9]+ s:|^ *i:"
```

Строки `i:` — издатели. Если сервер отдаёт только один сертификат (есть `0 s:`,
но нет `1 s:`), промежуточный он не присылает — тогда нужны и промежуточный,
и корневой.

**2. Выгрузить их из хранилища Windows в PEM** (PowerShell из корня
репозитория; подставьте часть имени издателя):

```powershell
$certs = Get-ChildItem Cert:\LocalMachine\Root, Cert:\LocalMachine\CA, Cert:\CurrentUser\Root, Cert:\CurrentUser\CA |
  Where-Object Subject -like '*Имя издателя*' |
  Sort-Object Thumbprint -Unique
$certs | Format-Table Subject, NotAfter
$pem = foreach ($c in $certs) {
  '-----BEGIN CERTIFICATE-----'
  [Convert]::ToBase64String($c.RawData, 'InsertLineBreaks')
  '-----END CERTIFICATE-----'
}
$pem | Set-Content -Encoding ascii certs\ca.pem
```

Если издатель — «Russian Trusted Root CA» или «Russian Trusted Sub CA»,
это сертификаты Минцифры: их можно скачать с Госуслуг и сложить в тот же файл.

**3. Проверить до сборки** (Git Bash) — должно быть `Verify return code: 0 (ok)`:

```bash
openssl s_client -connect nexus.corp:443 -servername nexus.corp -CAfile certs/ca.pem </dev/null 2>/dev/null | grep "Verify return code"
```

После этого `WDWS_PIP_TRUSTED_HOST` в `.env` можно очистить: pip тоже будет
проверять сертификат по той же цепочке, а не пропускать проверку.
