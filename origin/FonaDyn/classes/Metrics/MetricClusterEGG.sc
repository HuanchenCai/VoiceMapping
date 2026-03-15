// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

// This "metric" class is schizophrenic in that its palette must change
// when selectedCluster or nClusters are changed.
// Any retrieval of the .palette functions must be preceded
// by a call to .setClusters(which, howMany) where "which" is one of [0..nClusters] .

MetricClusterEGG : VRPMetric {
	classvar <metricNumber;		// the desired index of this metric in the menu
	classvar <symbol = \ClustersEGG;
	classvar <busName = \ClusterNumber;
	classvar <busRate = \audio;
	classvar <logFileTrack = 7;

	var fnMyPalette;
	var fnClusterColor;
	var <typeColor;
	var <nClusters = 3, <nCluster = 0;

	*new { arg number=nil, bDifference=false, file=nil;
		^super.new.init(number, bDifference, file);
	}

	paletteCluster { | typeColor, min, max |
		^{ | v |
			// Blend with white depending on the percentage
			var sat, cSat;
			sat = v.linlin(min, max, 0.1, 1.0);
			cSat = Color.white.blend(typeColor, sat);
			cSat
		};
	}

	init { arg number, bDiff=false, file;
		metricNumber = number ? VRPSettings.iClustersEGG;
		bDifferencing = bDiff;
		fnClusterColor =  { Color.magenta };  // dummy color
		if (file.notNil,
			{ this.configFromFile(file) },
			{ this.configFromCode() }
		);
	}

	setClusters { arg which=0, howMany=nil;
		var bReconfig = false;
		if (howMany.notNil and: (howMany != nClusters), {
			nClusters = howMany;
			bReconfig = true;
		});
		if (which != nCluster, {
			nCluster = which;
			bReconfig = true;
		});
		if (bReconfig, { this.configFromCode() });
		csvPrecision = if (which == 0, 1, 0.01);
	}

	configFromCode {
		menuText = "EGG waveshape clusters";	// String for the layers menu
		unit = "";								// Unit, if applicable, e.g. "dB"

		fnMyPalette = { | v |
			var cHue = v.linlin(0.0, nClusters, 0.0, 0.999);
			Color.hsv(cHue, 0.7, 1)
		};

		fnClusterColor = this.getColorPaletteDiscrete(fnMyPalette, nClusters);
		typeColor = fnClusterColor.value(nCluster-1);

		if (nCluster == 0,
			{
				csvName = "maxCluster";					// Column title in map files
				colorBarWarpType = \lin;				// Color axis \lin or \exp
				unit = "";								// Unit, if applicable, e.g. "dB"
				minVal = 1;
				maxVal = nClusters + 0.97;
				palette = { | v |
					var color, cHue, sat, cBlend;
					(v.class == Array).if(
						{	// invoked with [index, count]
							color = fnClusterColor.value(v[0]);
							cBlend = v[1].linlin(1, 100, 0, 1.0);
							color = Color.white.blend(color, blend: cBlend);
						},{ // invoked with index only
							color = fnClusterColor.value(v);
					});
					color
				};
				if (bDifferencing.not, {
					colorBarText = "EGG  cluster  #";		// String for the color bar
					trendText = "Whiter: more overlap";  	// String for info text
					trendTextColor = Color.white;
				}, {
					// Color mapping of delta-value
					colorBarText = "New EGG cluster #"; 	// Ditto, when differencing
					trendText = "White: no change";  		// String for info text
					trendTextColor = Color.white;
				});
			}, {
				csvName = "Cluster %";					// Column title in map files
				colorBarWarpType = \lin;				// Color axis \lin or \exp

				if (bDifferencing.not, {
					// Blend with white depending on the count. Counts >= 200 aren't blended at all.
					colorBarText = "EGG cluster #";			// String for the color bar
					minVal = 0;
					maxVal = 100.0;
					palette = { | v |
						var color; // , cHue, sat;
						(v.class == Array).if(
							{
								color = Color.white.blend(typeColor, blend: v[0].linlin(1, 100, 0.1, 1.0) );
							},{ // invoked with index only
								color = this.paletteCluster(typeColor, minVal, maxVal).value(v);
						});
						color
					};
					trendText = "% of all cycles"; // String for info text
					trendTextColor = fnClusterColor.value(nCluster-1);
					unit = "%";								// Unit, if applicable, e.g. "dB"
				}, {
					// Color mapping of delta-percent
					minVal = -100.0;
					maxVal = 100.0;
					palette = this.getColorPaletteDiff(index: 0);
					colorBarText = "Δ%, cluster #"; 	// Ditto, when differencing
					trendText = "→ Increase";  	// String for info text
					trendTextColor = palette.(maxVal);
					unit = "%Δ";								// Unit, if applicable, e.g. "dB"
				});
		});
	}

	////////////////////////////////////////////////////////////////////////
	// For Matlab colormap support:
	////////////////////////////////////////////////////////////////////////

	cFileMap {
		var rgbArray;
		var rgbArrayString = String.new;
		var retval = [];
		var pushMinVal, pushMaxVal;

		pushMinVal = minVal;		// Data are stored as 0..(nClusters-1)
		minVal = minVal-1;			// but the color scale runs from (1..nClusters)
		pushMaxVal = maxVal;
		maxVal = maxVal-1;

		retval = this.cMap(shades: nClusters);

		minVal = pushMinVal;
		maxVal = pushMaxVal;
		^retval
	}

	cMapDiff { arg shades=20;
		minVal = -100.0;
		maxVal = 100.0;
		palette = this.getColorPaletteDiff(index: 0);
		^this.cMap(shades, bLog: false);
	}

} /* MetricClusterEGG */

