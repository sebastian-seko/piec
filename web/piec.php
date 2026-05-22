<?php
$page = $_SERVER['PHP_SELF'];
$sec  = 10;

$data_file = "/data/odczyty.txt";
$error     = null;
$m         = [];

if (!file_exists($data_file)) {
    $error = "Brak pliku danych: $data_file";
} else {
    $raw = @file_get_contents($data_file);
    if ($raw === false) {
        $error = "Nie można odczytać: $data_file";
    } else {
        $m = explode(",", trim($raw));
        if (count($m) < 13) {
            $error = "Niekompletne dane w pliku ($data_file)";
        }
    }
}

if (!$error) {
    $tempCWU      = round((float)$m[0],  1);
    $tempCO       = round((float)$m[1],  1);
    $tempDwor     = round((float)$m[2],  1);
    $tempPalnik   = round((float)$m[3],  1);
    $tempMieszacz = round((float)$m[4],  1);
    $stan         = trim($m[5]);
    $setCO        = (int)$m[6];
    $setCWU       = (int)$m[7];
    $setMieszacz  = (int)$m[8];
    $nadmuch      = (int)$m[9];
    $mieszaczProc = (int)$m[10];
    $mocKotla     = round((float)$m[12], 1);
}

$status_colors = [
    'PRACA'        => '#27ae60',
    'ROZPALANIE'   => '#e67e22',
    'WYGASZANIE'   => '#e67e22',
    'WYŁĄCZONY'    => '#7f8c8d',
    'POSTÓJ'       => '#3498db',
    'PRACA RĘCZNA' => '#9b59b6',
    'ALARM'        => '#e74c3c',
    'CZYSZCZENIE'  => '#f39c12',
];
$stan_color = isset($status_colors[$stan]) ? $status_colors[$stan] : '#95a5a6';
?>
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="<?php echo $sec; ?>;URL='<?php echo htmlspecialchars($page); ?>'">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <title>Piec</title>
    <style>
        * { margin: 0; padding: 0; -webkit-box-sizing: border-box; box-sizing: border-box; }

        body {
            background: #1a1a2e;
            color: #ecf0f1;
            font-family: -apple-system, Helvetica, Arial, sans-serif;
            min-height: 100%;
        }

        /* STATUS BAR */
        .status-bar {
            text-align: center;
            padding: 18px 10px;
            font-size: 28px;
            font-weight: bold;
            letter-spacing: 3px;
            background: <?php echo $stan_color; ?>;
            -webkit-box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            text-shadow: 0 1px 3px rgba(0,0,0,0.4);
        }

        /* GRID */
        .grid { padding: 12px; }
        .grid:after { content: ""; display: table; clear: both; }

        .card {
            float: left;
            width: 50%;
            padding: 6px;
        }

        .card-inner {
            background: #16213e;
            -webkit-border-radius: 12px;
            border-radius: 12px;
            padding: 16px 12px;
            -webkit-box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            min-height: 110px;
            position: relative;
        }

        .card-label {
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #7f8c8d;
            margin-bottom: 6px;
        }

        .card-value {
            font-size: 42px;
            font-weight: bold;
            line-height: 1;
            color: #ecf0f1;
        }

        .card-unit {
            font-size: 18px;
            color: #bdc3c7;
        }

        .card-sub {
            font-size: 13px;
            color: #7f8c8d;
            margin-top: 6px;
        }

        .card-sub span {
            color: #bdc3c7;
        }

        /* ACCENT COLORS per card */
        .accent-co     .card-value { color: #e74c3c; }
        .accent-cwu    .card-value { color: #3498db; }
        .accent-dwor   .card-value { color: #1abc9c; }
        .accent-palnik .card-value { color: #e67e22; }
        .accent-moc    .card-value { color: #f1c40f; }
        .accent-nadm   .card-value { color: #9b59b6; }
        .accent-miesz  .card-value { color: #2ecc71; }

        /* BAR */
        .bar-bg {
            background: #0f3460;
            -webkit-border-radius: 4px;
            border-radius: 4px;
            height: 6px;
            margin-top: 8px;
            overflow: hidden;
        }
        .bar-fill {
            height: 6px;
            -webkit-border-radius: 4px;
            border-radius: 4px;
        }

        /* FOOTER */
        .footer {
            text-align: center;
            font-size: 12px;
            color: #4a4a6a;
            padding: 8px;
        }

        /* ERROR */
        .error-box {
            margin: 30px;
            background: #e74c3c;
            -webkit-border-radius: 10px;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            font-size: 18px;
        }
    </style>
</head>
<body>

<?php if ($error): ?>
    <div class="status-bar" style="background:#e74c3c;">BŁĄD</div>
    <div class="error-box"><?php echo htmlspecialchars($error); ?></div>
<?php else: ?>

<div class="status-bar"><?php echo htmlspecialchars($stan); ?></div>

<div class="grid">

    <!-- CO -->
    <div class="card">
        <div class="card-inner accent-co">
            <div class="card-label">&#127777; CO</div>
            <div class="card-value"><?php echo $tempCO; ?><span class="card-unit">°C</span></div>
            <div class="card-sub">Zadana: <span><?php echo $setCO; ?> °C</span></div>
            <div class="bar-bg"><div class="bar-fill" style="width:<?php echo min(100, $setCO > 0 ? round($tempCO/$setCO*100) : 0); ?>%;background:#e74c3c;"></div></div>
        </div>
    </div>

    <!-- CWU -->
    <div class="card">
        <div class="card-inner accent-cwu">
            <div class="card-label">&#128167; CWU</div>
            <div class="card-value"><?php echo $tempCWU; ?><span class="card-unit">°C</span></div>
            <div class="card-sub">Zadana: <span><?php echo $setCWU; ?> °C</span></div>
            <div class="bar-bg"><div class="bar-fill" style="width:<?php echo min(100, $setCWU > 0 ? round($tempCWU/$setCWU*100) : 0); ?>%;background:#3498db;"></div></div>
        </div>
    </div>

    <!-- DWÓR -->
    <div class="card">
        <div class="card-inner accent-dwor">
            <div class="card-label">&#9729; Dwór</div>
            <div class="card-value"><?php echo $tempDwor; ?><span class="card-unit">°C</span></div>
        </div>
    </div>

    <!-- PALNIK -->
    <div class="card">
        <div class="card-inner accent-palnik">
            <div class="card-label">&#128293; Palnik</div>
            <div class="card-value"><?php echo $tempPalnik; ?><span class="card-unit">°C</span></div>
        </div>
    </div>

    <!-- MIESZACZ -->
    <div class="card">
        <div class="card-inner accent-miesz">
            <div class="card-label">&#8652; Mieszacz</div>
            <div class="card-value"><?php echo $tempMieszacz; ?><span class="card-unit">°C</span></div>
            <div class="card-sub">Zad: <span><?php echo $setMieszacz; ?> °C</span> &nbsp; Otw: <span><?php echo $mieszaczProc; ?> %</span></div>
            <div class="bar-bg"><div class="bar-fill" style="width:<?php echo min(100,$mieszaczProc); ?>%;background:#2ecc71;"></div></div>
        </div>
    </div>

    <!-- NADMUCH -->
    <div class="card">
        <div class="card-inner accent-nadm">
            <div class="card-label">&#127788; Nadmuch</div>
            <div class="card-value"><?php echo $nadmuch; ?><span class="card-unit">%</span></div>
            <div class="bar-bg"><div class="bar-fill" style="width:<?php echo min(100,$nadmuch); ?>%;background:#9b59b6;"></div></div>
        </div>
    </div>

    <!-- MOC -->
    <div class="card">
        <div class="card-inner accent-moc">
            <div class="card-label">&#9889; Moc kotła</div>
            <div class="card-value"><?php echo $mocKotla; ?><span class="card-unit">kW</span></div>
            <div class="bar-bg"><div class="bar-fill" style="width:<?php echo min(100,$mocKotla); ?>%;background:#f1c40f;"></div></div>
        </div>
    </div>

</div>

<div class="footer">
    Odświeżanie co <?php echo $sec; ?>s &nbsp;|&nbsp; <?php echo date('H:i:s'); ?>
</div>

<?php endif; ?>
</body>
</html>
