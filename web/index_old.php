     <?php

	 $page = $_SERVER['PHP_SELF'];
$sec = "10";

   
	
	
	?>
<html>
    <head>
    <meta http-equiv="refresh" content="<?php echo $sec?>;URL='<?php echo $page?>'">
    </head>
    <body>
	<p style="font-size: 1.3cm">
	<?php
    $data = json_decode(@file_get_contents("/data/odczyty.json"), true);
    $o = (is_array($data) && isset($data['odczyty'])) ? $data['odczyty'] : null;
    if ($o === null) { echo "Brak lub niepoprawny /data/odczyty.json<br>"; }
    // dawny uklad pozycyjny, zeby reszta pliku dzialala bez zmian
    $matches1 = $o === null ? array_fill(0, 13, 0) : [
        $o['cwu'], $o['co'], $o['dwor'], $o['palnik'], $o['mieszacz'], $o['stan'],
        $o['zadana_co'], $o['zadana_cwu'], $o['zadana_mieszacz'], $o['nadmuch'],
        $o['mieszacz_otwarcie'], $o['strumien_paliwa'], $o['moc'],
    ];
    $stan = $matches1[5];
    // Output the temperature
    echo "Stan = ";
	print  $stan; 
	echo "<br>";
    $temperature1 = $matches1[2];
	$temperature1=round($temperature1,2);
    // Output the temperature
    echo "Dwór = ";
	print  $temperature1; 
	echo " °C";
	echo "<br>";
    $tempCWU = $matches1[0];
	$tempCWU=round($tempCWU,2);
    echo "CWU = ";
	print  $tempCWU; 
	echo " °C | Zadana = ";
    print  $matches1[7];
	echo " °C <br>";
    $tempCO = $matches1[1];
	$tempCO=round($tempCO,2);
    echo "CO = ";
	print  $tempCO; 
    echo " °C | Zadana =";
    print  $matches1[6];
	echo " °C <br>";
    $tempMieszacza = $matches1[4];
	$tempMieszacza=round($tempMieszacza,2);
    echo "Miesz = ";
	print  $tempMieszacza; 
	echo "°C | Zad = ";
    print  $matches1[8];
	echo "°C | ";
    print  $matches1[10];
    echo "% <br>";
    $temppalnika = $matches1[3];
	$temppalnika=round($temppalnika,2);
    echo "Palnik = ";
	print  $temppalnika; 
	echo " °C";
	echo "<br>";
    echo "Nadmuch = ";
	print  $matches1[9]; 
	echo " %";
	echo "<br>";
    ?>
	<?php

?>



	</p>
    </body>
</html>
