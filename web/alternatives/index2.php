<!DOCTYPE html>
<html>
<?php
        if (!defined("THERMOMETER_SENSOR_PATH1")) define("THERMOMETER_SENSOR_PATH1", "/data/odczyty.txt"); 
         $thermometer1 = fopen(THERMOMETER_SENSOR_PATH1, "r"); 
         $thermometerReadings1 = fread($thermometer1, filesize(THERMOMETER_SENSOR_PATH1)); 
         fclose($thermometer1); 
         $matches1 = explode(",", $thermometerReadings1);
	 $page = $_SERVER['PHP_SELF'];
	 $sec = "10";
?>
<head>
<link rel="stylesheet" href="style.css">
<meta http-equiv="refresh" content="<?php echo $sec?>;URL='<?php echo $page?>'">
</head>
<body>
 </div>
  <h1 class="title"></h1>
  <div id="container">
    <div class="pricetab">
      <h1> Dwor </h1>
      <div class="price"> 
        <h5><?php $temperature1 = $matches1[2];
          $temperature1=round($temperature1,2);
          print  $temperature1; ?><sup>o</sup>C</h5> 
      </div>

      <div class="pricefooter">

      </div>
    </div>
    <div class="pricetab">
      <h1> CO </h1>
      <div class="price"> 
        <h2><?php $tempCO = $matches1[1];
          $tempCO=round($tempCO,2);
            print  $tempCO; ?><sup>o</sup>C </h2> 
        <h3> <?php print  $matches1[6]; ?><sup>o</sup>C </h3> 
      </div>

      <div class="pricefooter">

      </div>
    </div>

    <div class="pricetab">
      <h1> Status </h1>
      <div class="price"> 
                <h4><?php
         $stan = $matches1[5];
       print  $stan; ?></h4>  
      </div>

      <div class="pricefooter">

      </div>
    </div>
    <div class="pricetab">
      <h1> CWU </h1>
      <div class="price"> 
        <h2><?php $tempCWU = $matches1[0];
          $tempCWU=round($tempCWU,2);
          print  $tempCWU; ?><sup>o</sup>C </h2> 
        <h3><?php print  $matches1[7]; ?><sup>o</sup>C </h3> 
      </div>
      <div class="pricefooter">

      </div>
    </div>
    <div class="pricetab">
      <h1> Palnik </h1>
      <div class="price"> 
        <h5><?php $temppalnika = $matches1[3];
          $temppalnika=round($temppalnika,2); print $temppalnika; ?><sup>o</sup>C</h5> 
      </div>

      <div class="pricefooter">

      </div>
    </div>
    <div class="pricetab">
      <h1> Mieszacz </h1>
      <div class="price"> 
        <h2><?php $tempMieszacza = $matches1[4];
          $tempMieszacza=round($tempMieszacza,2);
            print  $tempMieszacza; ?><sup>o</sup>C </h2> 
        <h3><?php print  $matches1[8]; ?><sup>o</sup>C </h3> 
      </div>
      <div class="pricefooter"></div>
    </div>

      </div>
      
    </div>
  </div>
</body>
