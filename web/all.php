<?php
header('Content-Type: application/json');
define("ODCZYTY_JSON", "/data/odczyty.json");

$raw  = @file_get_contents(ODCZYTY_JSON);
$data = $raw === false ? null : json_decode($raw, true);
if (!is_array($data) || !isset($data['odczyty'], $data['serwis'], $data['wyjscia'])) {
    http_response_code(503);
    echo json_encode(["error" => "Brak lub niepoprawny " . ODCZYTY_JSON], JSON_UNESCAPED_UNICODE);
    exit;
}

$o = $data['odczyty'];
$s = $data['serwis'];
$w = $data['wyjscia'];

$result = [
    "cwu" => (float)$o['cwu'],
    "co" => (float)$o['co'],
    "dwor" => (float)$o['dwor'],
    "palnik" => (float)$o['palnik'],
    "mieszacz" => (float)$o['mieszacz'],
    "stan" => (string)$o['stan'],
    "zadana_co" => (int)$o['zadana_co'],
    "zadana_cwu" => (int)$o['zadana_cwu'],
    "zadana_mieszacz" => (int)$o['zadana_mieszacz'],
    "nadmuch" => (int)$o['nadmuch'],
    "mieszacz_otwarcie" => (int)$o['mieszacz_otwarcie'],
    "mieszacz_status" => (string)$o['mieszacz_status'],
    "strumien_paliwa" => (float)$o['strumien_paliwa'],
    "moc" => (float)$o['moc'],
    "plomien" => (float)$o['plomien'],
    "praca_max_h" => (int)$s['praca_max_h'],
    "praca_sred_h" => (int)$s['praca_sred_h'],
    "praca_min_h" => (int)$s['praca_min_h'],
    "zaplony" => (int)$s['zaplony'],
    "podajnik_czas_h" => (int)$s['podajnik_czas_h'],
    "pompa_mieszacz" => (bool)$w['pompa_mieszacz'],
    "pompa_cwu" => (bool)$w['pompa_cwu'],
    "pompa_piec" => (bool)$w['pompa_piec'],
    "zapalarka" => (bool)$w['zapalarka'],
    "silownik_czyszczacy" => (bool)$w['silownik_czyszczacy'],
    "podajnik_2" => (bool)$w['podajnik_2'],
    "podajnik" => (bool)$w['podajnik'],
    "wentylator" => (bool)$w['wentylator'],
    "alarm" => isset($data['alarm']) ? (bool)$data['alarm']['aktywny'] : null,
    "alarm_kod" => $data['alarm']['kod'] ?? null,
    "alarm_bajt_198" => $data['alarm']['bajt_198'] ?? null,
    "wyjscia2" => $data['alarm']['wyjscia2'] ?? null,
    "odczyt" => $data['timestamp'],
    "timestamp" => date('c')
];

echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
