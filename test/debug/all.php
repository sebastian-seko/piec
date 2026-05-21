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
    //$stan = $matches1[5];
    // Output the temperature
    //echo "Stan = ";
	print_r($matches1); 
?>
