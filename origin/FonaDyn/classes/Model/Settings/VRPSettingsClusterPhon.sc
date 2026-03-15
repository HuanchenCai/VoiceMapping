// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
VRPSettingsClusterPhon {
	var <>isVisible;
	var <>pointsInCluster; 	// Pre-learned point (cycle) counts to be sent to the server on init
	var <>centroids;		// Pre-learned centroid coordinates to be sent to the server on init
	var <>clusterLabels;	// Array with an optional descriptive label for each cluster
	var <>rangeLows;		// Array of lower bounds for metric rescaling
	var <>rangeHighs;		// Array of higher bounds for metric rescaling
	var <>clusterMetrics;	// Array of symbols for the "features" that are used for clustering
	var <busTable;			// Array of bus numbers, busrates, multipliers and offsets
	var <>initialize;		// True if centroids should be preloaded at start
	var <>learn; 			// Whether the clustering algorithm should learn from the data
	             				// or simply use prelearned data to classify incoming points
	var <>reset; 			// Whether to allow resets in the data or not; a reset will reset
	             				// learned data (essentially replace it with initial values)
	var <>autoReset; 		// Whether FonaDyn will reset the cluster data itself
								// after the first interval of phonation above the clarity threshold
	var <>iFramesToReset; 	// The number of GUI updates to phonate before Auto Reset
	var <>filePath;  		// File in which the current cluster data are stored
	var <>mapCentroid;      // all 9 coordinates of one centroid, from a map
	var <>mapCentroidNumber;  // which centroid to set from the map
	var <stashRequested;	// Bool for valid newSettings
	var <newSettings;		// New settings that were just loaded; or nil
	var nC;					// Number of clusters to request

	classvar nMinClusters = 2;
	classvar <nMaxClusters = 10;
	classvar <nMinMetrics = 1;
	classvar <nMaxMetrics = 10;
	classvar <defaultMetrics; 	// Array of ID's of metrics that will be used by default


	*new { | old |
		^super.new.init(old);
	}

	requestStash { arg clusterPhonSettings;
		if (stashRequested = clusterPhonSettings.notNil) {
			newSettings = clusterPhonSettings;
		};
	}

	getSettings {
		stashRequested = false;
		^newSettings
	}

	nMetrics {
		^clusterMetrics.size;
	}

	nClusters {
		if ((nC = pointsInCluster.size) < nMinClusters, { nC = nMinClusters });
		^nC
	}

	allocCentroids { | n, arrayMetrics=nil |
		if (arrayMetrics.notNil, { clusterMetrics = arrayMetrics });
		// Set up dummy centroids to start with
		if (n.inclusivelyBetween(nMinClusters, nMaxClusters), {
			nC = n;
			pointsInCluster = 10 ! nC;		 // Avoid zero counts for manually seeded centroids

			// Make an initial "cobweb" in the radar plot
			centroids = (1.0, 0.9..((11-nC)*0.1)).dup(clusterMetrics.size).flop;

			clusterLabels = "<not named>" ! nC;
			rangeLows  = -0.01 ! clusterMetrics.size;
			rangeHighs = 1.01 ! clusterMetrics.size;
			VRPSettings.metrics[0..VRPSettings.iLastMetric] do: { arg met, i;
				var mx = met.class.symbol;
				var ix = clusterMetrics.indexOf(mx);
				var msg;
				if (ix.notNil, {
					msg = met.fnStandardizeMsg.value;
					rangeLows[ix]  = msg[1];
					rangeHighs[ix] = msg[2];
				}
			)};
		}, {
			"Too many clusters requested".error;
		});
	}

	makeBusTable {
		busTable = [nil ! 4] dup: clusterMetrics.size;

		//// VRPSettings.iLastMetric is the highest index of any non-clustered metric
		VRPSettings.metrics[0..VRPSettings.iLastMetric] do: { arg met, i;
			var mx = met.class.symbol;
			var ix = clusterMetrics.indexOf(mx);
			var msg, newMsg;

			if (ix.notNil, {
				// Get the default values
				msg = met.fnStandardizeMsg.value;

				// Override with current ranges
				msg[1] = rangeLows[ix];
				msg[2] = rangeHighs[ix];

								// symbol,         \audio or \control,	\busNum, \std-perform-msg
				busTable[ix] = [met.class.busName, met.class.busRate,   -1,      msg];
			});
		};
		busTable
	}

	init { | old=nil |
		defaultMetrics = [
			VRPSettings.icppSmoothed,
			VRPSettings.iCrestFactor,
			VRPSettings.iSpecBal,
			VRPSettings.iEntropy,
			VRPSettings.iQcontact,
			VRPSettings.idEGGmax
			// VRPSettings.iHRFEGG
		];
		clusterMetrics = defaultMetrics collect: { | id, ix |
			VRPSettings.metrics[id.asInteger].class.symbol;
		};

		this.allocCentroids(5); // dummy clusters to start with

		learn = true;
		reset = true;
		initialize = false;
		autoReset = false;
		if (old.notNil, {
			learn = old.learn;
			initialize = old.initialize;
			autoReset = old.autoReset;
			reset = old.reset;
		});

		rangeLows = [];
		rangeHighs = [];
		iFramesToReset = 5;  // Refresh rate is normally 24 Hz, so 5 frames are ca 200 ms.
		stashRequested = false;
		newSettings = nil;
		mapCentroid = nil;
		mapCentroidNumber = 0;
		isVisible = true;
	}

	loadClusterPhonSettings { arg path;
		var cArray=nil, c=0;
		var newFeatures = [];
		var nMetrics = 0;

		if (PathName.new(path).isFile, {
			cArray = FileReader.read(path, skipEmptyLines: true, skipBlanks: true, delimiter: VRPMain.cListSeparator);
			// If the first row contains only one element, it might be comma-delimited (not semicolon).
			// Try to parse it as such. This saves hassle when reading CSV files from elsewhere.
			if (cArray[0].size == 1, {
				cArray.clear;
				cArray = FileReader.read(path, skipEmptyLines: true, skipBlanks: true, delimiter: $,);
			});
		}, {
			format("File % not found", path.quote).error;
		});

		if (cArray.notNil, {
			// Remove trailing empty cells caused by delimiter(s) at the end of a line
			cArray do: { | row, ix | while { row.last.isEmpty } { row.pop } };

			// Parse header row [0] as column names, skipping "Metrics" in column 0
			cArray[0][1..] do: { | c, ic |
				var bFound = false;
				VRPSettings.metrics do: { | m, jx |
					if (m.csvName == c, {
						newFeatures = newFeatures.add(m.class.symbol);
						bFound = true;
					});
				};
				if (bFound.not, {
					format("Unrecognized metric: \"%\", in %", c, path).error;
				});
			}
		});

		try {	// Small check for errors
			nMetrics = newFeatures.size;
			if (nMetrics.inclusivelyBetween(nMinMetrics, nMaxMetrics).not
				{
					Error("Bad input file, invalid # of metrics").throw;
				}
			);

			// Get row [1] of rangeLows, skipping "0%" in column 0
			rangeLows = cArray[1][1..].asFloat;

			// Get row [2] of rangeHighs, skipping "100%" in column 0
			rangeHighs = cArray[2][1..].asFloat;

			// Now parse the centroid cycle counts
			c = cArray.size - 3;
			pointsInCluster = c collect: { | ix | cArray[3+ix][0].asInteger };

			// ... and the centroid values
			centroids = Array.fill2D(c, nMetrics, { arg row, col; cArray[row+3][col+1].asFloat });
			clusterMetrics = newFeatures;

			// Load cluster labels, if any, from the last column, else nil
			clusterLabels = Array.fill(c, { |i| cArray[i+3][nMetrics+1] });

			// Init some other bits and sundry
			filePath = path;
			nC = c;
			initialize = true;
			learn = false;
			("    Loaded" + path).postln;
		} {
			// Something went wrong
			pointsInCluster = nil;
			centroids = nil;
			nMetrics = c = 0;
			initialize = false;
			"Load CSV failed".postln;
		};
		^[c, nMetrics]  // return nClusters and nFeatures
	} /*  loadClusterPhonSettings */

	saveClusterPhonSettings { | path |
		var cDelim = VRPMain.cListSeparator;
		var dim = clusterMetrics.size;

		if (path.endsWith(".csv").not) {
			path = path ++ "_cPhon.csv";
		};

		File.use(path, "w", { | file |

			// Write header row with "Metrics" and column names (not symbols)
			file << "Metric";
			clusterMetrics do: { | f, ix |
				VRPSettings.metrics do: { | m, jx |
					if (m.class.symbol == f, {
						file.put(cDelim);
						file << m.csvName;
					})
				}
			};
			file.put($\r); file.nl;

			// Write row with "0%" and low-range values
			file << "0%";
			rangeLows do: { | v |
				file.put(cDelim);
				file << v;
			};
			file.put($\r); file.nl;

			// Write row with "100%" and high-range values
			file << "100%";
			rangeHighs do: { | v |
				file.put(cDelim);
				file << v;
			};
			file.put($\r); file.nl;

			// Write one row for each centroid
			centroids do: { | centr, ix |
				var labelStr, points;

				points = pointsInCluster[ix].asInteger;
				if (points == 0, { points = 10 }); 		// should not happen, but...
				file << points;
				file.put(cDelim);
				centr do: { | value, i |
					file << value;
					if (i < (dim - 1), {file.put(cDelim)} );
				};

				// Write the cluster description text, if any
				if ((labelStr = clusterLabels[ix]).notNil, {
					file.put(cDelim);
					file << labelStr;
				});

				file.put($\r); file.nl;
			}
		});
		("Saved" + path).postln;
	} /* saveClusterPhonSettings */
}