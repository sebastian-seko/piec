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
     if (!defined("THERMOMETER_SENSOR_PATH1")) define("THERMOMETER_SENSOR_PATH1", "/data/odczyty.txt"); 
    // Open resource file for thermometer
    $thermometer1 = fopen(THERMOMETER_SENSOR_PATH1, "r"); 
    // Get the contents of the resource
    $thermometerReadings1 = fread($thermometer1, filesize(THERMOMETER_SENSOR_PATH1)); 
    // Close resource file for thermometer
    fclose($thermometer1); 
    // We're only interested in the 2nd line, and the value after the t= on the 2nd line
    //preg_match("/t=(.+)/", preg_split("/\n/", $thermometerReadings1)[1], $matches1);
    $matches1 = explode(",", $thermometerReadings1);
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
    echo "Mieszacz = ";
	print  $tempMieszacza; 
	echo " °C | Zadana = ";
    print  $matches1[8];
	echo " °C <br>";
    $temppalnika = $matches1[3];
	$temppalnika=round($temppalnika,2);
    echo "Palnik = ";
	print  $temppalnika; 
	echo " °C";
	echo "<br>";
    ?>
	<?php

?>



	</p>
    </body>
</html>
