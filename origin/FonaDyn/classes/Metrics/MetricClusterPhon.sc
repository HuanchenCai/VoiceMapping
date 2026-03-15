// Copyright (C) 2016-2024 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

// This "metric" class is schizophrenic in that its palette must change
// when selectedCluster or nClusters are changed.
// Any retrieval of the .palette functions must be preceded
// by a call to .setClusters(which, howMany) where "which" is one of [0..nClusters] .


MetricClusterPhon : VRPMetric {
	classvar <metricNumber;		// the desired index of this metric in the menu
	classvar <symbol = \ClustersPhon;
	classvar <busName = \ClusterPhonNumber;
	classvar <busRate = \control;
	classvar <logFileTrack = 8;

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
		metricNumber = number ? VRPSettings.iClustersPhon;
		bDifferencing = bDiff;
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
		// this.configFromCode();
	}

	configFromCode {
		menuText = "Phonation type clusters";	// String for the layers menu
		unit = "";								// Unit, if applicable, e.g. "dB"

		fnMyPalette = { arg v;
			var inScaled, cHue, cSat, cValue;
			inScaled = 1.min((v+1)/(nClusters+1));
			cHue = [0.65, 0.1][(1.01*inScaled).round(1).asInteger];
			cHue = cHue + (0.12 * (0.5 - inScaled));
			cValue = inScaled.bilin(0.5, 0, 1.0, 0.95, 0.3, 0.3);
			cSat = 1 - (0.7*cValue);
			Color.hsv(cHue, cSat, cValue)
		};

		fnClusterColor = this.getColorPaletteDiscrete(fnMyPalette, nClusters);
		typeColor = fnClusterColor.value(nCluster-1);

		if (nCluster == 0,
			{
				csvName = "maxCPhon";	// Column title in map files
				colorBarText = "Type cluster #";		// String for the color bar
				colorBarWarpType = \lin;				// Color axis \lin or \exp
				unit = "";								// Unit, if applicable, e.g. "dB"
				minVal = 1;
				maxVal = nClusters+0.97;
				palette = { | v |
					var color, cHue, cBlend;
					(v.class == Array).if(
						{	// invoked with [index, count]
							color = fnClusterColor.value(v[0]);
							cBlend = v[1].linlin(1, 100, 0, 1.0);
							color = Color.white.blend(color, blend: cBlend);
						},{ // invoked with index only
							color = fnClusterColor.value(v);
						}
					);
					color
				};
				if (bDifferencing.not, {
					trendText = "Whiter: more overlap";  	// String for info text
					trendTextColor = Color.white;
				}, {
					// Color mapping of delta-value; not applicable here
					colorBarText = "New type cluster #"; // Ditto, when differencing
					trendText = "White: no change";  	// String for info text
					trendTextColor = Color.white;
				});
			}, {
				csvName = "cPhon %";	// Column title in map files
				colorBarWarpType = \lin;				// Color axis \lin or \exp

				if (bDifferencing.not, {
					// Blend with white depending on the count. Counts >= 200 aren't blended at all.
					colorBarText = "Phon type #";			// String for the color bar
					minVal = 0;
					maxVal = 100.0;
					// palette = this.paletteCluster(typeColor, minVal, maxVal);
					palette = { | v |
						var color, cHue, sat;
						(v.class == Array).if(
							{	// invoked with [percent, cycles]
								sat = v[0].linlin(1, 100, 0.1, 1.0);
								color = Color.white.blend(typeColor, sat);
							},{ // invoked with cycles only
								color = this.paletteCluster(typeColor, minVal, maxVal).value(v);
						});
						color
					};
					colorBarText = "Type #";		// String for the color bar
					trendText = "% of all cycles"; 			// String for info text
					trendTextColor = fnClusterColor.value(nCluster-1);
					unit = "%";								// Unit, if applicable, e.g. "dB"
				}, {
					// Color mapping of delta-percent
					minVal = -100.0;
					maxVal = 100.0;
					palette = this.getColorPaletteDiff(index: 0);
					colorBarText = "Δ% in type #"; 		// Ditto, when differencing
					trendText = "→ increase";  				// String for info text
					trendTextColor = palette.(maxVal);
					unit = "%Δ";							// Unit, if applicable, e.g. "dB"
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

		retval = this.cMap(nClusters);

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

} /* MetricClusterPhon */

