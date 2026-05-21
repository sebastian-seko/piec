<?php
header('Content-Type: application/json');

define("THERMOMETER_SENSOR_PATH1", "/data/odczyty.txt");

$data = file_get_contents(THERMOMETER_SENSOR_PATH1);
$values = array_map('trim', explode(',', $data));

$result = [
    "cwu" => (float)$values[0],
    "co" => (float)$values[1],
    "dwor" => (float)$values[2],
    "palnik" => (float)$values[3],
    "mieszacz" => (float)$values[4],
    "stan" => (string)$values[5],
    "zadana_co" => (float)$values[6],
    "zadana_cwu" => (float)$values[7],
    "zadana_mieszacz" => (float)$values[8],
    "nadmuch" => (int)$values[9],
    "mieszacz_otwarcie" => (int)$values[10],
    "strumien_paliwa" => (float)$values[11],
    "moc" => (float)$values[12],
    "mieszacz_status" => (string)$values[13],
    "moc_max" => (int)$values[14],
    "moc_med" => (int)$values[15],
    "moc_min" => (int)$values[16],
    "podajnik_czas" => (int)$values[17],
    "zaplony" => (int)$values[18],
    "pompa_mieszacz" => trim($values[19]) === "ON",
    "pompa_cwu" => trim($values[20]) === "ON",
    "pompa_piec" => trim($values[21]) === "ON",
    "zapalarka" => trim($values[22]) === "ON",
    "silownik_czyszczacy" => trim($values[23]) === "ON",
    "podajnik_2" => trim($values[24]) === "ON",
    "podajnik" => trim($values[25]) === "ON",
    "wentylator" => trim($values[26]) === "ON",
    "timestamp" => date('c')
];

echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
