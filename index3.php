     <?php

	 $page = $_SERVER['PHP_SELF'];
     $sec = "10";
     $myAudioFile = "625msljet.wav";

   
	
	
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
    if ($stan == ' ROZPALANIE') {
        echo '<body style="background-color:orange">';
        // echo '<EMBED SRC="'.$myAudioFile.'" HIDDEN="TRUE" AUTOSTART="TRUE"></EMBED>';
        echo '<audio src="625msljet.wav" autoplay="true" loop="loop">';
        } else {
        echo '<body style="background-color:white">';
        // echo '<EMBED SRC="'.$myAudioFile.'" HIDDEN="TRUE" AUTOSTART="FALSE"></EMBED>';
        echo '<audio src="625msljet.wav" autoplay="false" loop="loop">';
        }
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
