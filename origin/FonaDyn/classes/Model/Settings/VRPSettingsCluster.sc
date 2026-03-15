// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPSettingsCluster {
	var <>isVisible;
	var <>pointsInCluster; 	// Pre-learned point (cycle) counts to be sent to the server on init
	var <>centroids;		// Pre-learned centroid coordinates to be sent to the server on init
	var <nHarmonics; 		// The number of harmonics used to produce the points
	var <nDimensions; 		// The dimensionality of the points
	var <>initialize;  		// True if centroids should be preloaded at start
	var <>learn; 			// Whether the clustering algorithm should learn from the data or
	             				// simply use prelearnt data to classify incoming points
	var <>reset; 			// Whether to allow resets in the data or not; a reset will reset
	             				// learned data (essentially replace it with initial values)
	var <>autoReset; 		// Whether FonaDyn will reset the cluster data itself
								// after the first interval of phonation above the clarity threshold
	var <>iFramesToReset; 	// The number of GUI updates to phonate before Auto Reset

	var <>filePath;  		// File in which the current cluster data are stored
	var <>nSamples; 		// # of samples to estimate the cycles
	var <>smoothFactor; 	// Smooth factor for the SmoothedClusterCycle
	var <>suppressGibbs;	// True to unripple the re-synthesized wave shapes
	var <>pleaseStashThis;

	var nC; // Number of clusters
	classvar <nMinClusters = 2;
	classvar <nMaxClusters = 20;
	classvar <nMinHarmonics = 2;
	classvar <nMaxHarmonics = 20;

	nHarmonics_ { | n |
		nHarmonics = n;
		nDimensions = 3 * n ; // for clustering by dLevel, cos(dPhi) and sin(dPhi)
	}

	*new { | old=nil |
		^super.new.init(old);
	}

	nClusters {
		^nC
	}

	allocCentroids { | n, nh |
		if (n.inclusivelyBetween(nMinClusters, nMaxClusters), {
			// Set up dummy centroids to start with
			nC = n;
			pointsInCluster = 0 ! nC;
			centroids = 0.0 ! nDimensions ! nC;
		});
	}

	init { | old |
		this.nHarmonics_(10);
		nC = 5;
		this.allocCentroids(nC, nHarmonics); // dummy clusters to start with

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

		iFramesToReset = 5;  // Refresh rate is normally 24 Hz, so 5 frames are 208 ms.
		initialize = false;
		suppressGibbs = false;
		pleaseStashThis = nil;
		nSamples = 100;
		smoothFactor = 0.995; // Keep 99.5% of the old value and take 0.5% of the new value
		isVisible = true;
	}

	loadClusterSettings { arg path;
		var bNew, cArray=nil, c=0, d, h=0;

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
			// Remove any trailing empty cells caused by delimiter(s) at the end of a line
			cArray do: { | row, ix | while { row.last.isEmpty } { row.pop } };

			if (cArray[0].size < 4,
				{	// Old cluster-file format; still needed for revisiting old studies
					bNew = false;
					// Read the number of clusters and the dimensionality of the centroids
					c = cArray[0][0].asInteger;
					d = cArray[0][1].asInteger;
					// Read the cluster counts
					pointsInCluster = c collect: { | i | cArray[1][i].asInteger };
					centroids = Array.fill2D(c, d, { arg row, col; cArray[row+2][col].asFloat });
				}, { 	// New cluster-file format
					bNew = true;
					c = cArray.size;			// number of rows
					d = cArray[0].size - 1;		// number of columns, less one
					// Read the cluster counts
					pointsInCluster = c collect: { | i | cArray[i][0].asInteger };
					// Read the centroids
					centroids = Array.fill2D(c, d, { arg row, col; cArray[row][col+1].asFloat });
				}
			);

			h = (d/3).asInteger;

			try {
				// Small check for errors
				if ( c.inclusivelyBetween(nMinClusters, nMaxClusters).not
					or: h.inclusivelyBetween(nMinHarmonics, nMaxHarmonics).not,
					{
						Error("Bad input file, invalid # of clusters/harmonics").throw;
					}
				);

				nC = c;
				initialize = true;
				learn = false;
				this.nHarmonics_(h);
				filePath = path;
				("    Loaded" + path).postln;
				this.patchNewL1column;
			} {
				pointsInCluster = nil;
				centroids = nil;
				filePath = nil;
				initialize = false;
				nC = 0;
				c = h = 0;
				"Load CSV failed".warn;
			};
		});
		^[c, h]  // return nClusters and nHarmonics
	} /*  loadClusterSettings */

	patchNewL1column {
		var bOld=false;
		var n = this.nHarmonics-1;
		var fn = PathName(filePath).fileName;
		centroids do: { | lBel, ix |
			var roundBel = lBel[n].round(0.05);
			if (roundBel != 0.0, {
				bOld = true;
				centroids[ix][n] = 0.0;
			});
		};
		if (bOld, {
			format("File % with % harmonics is in an older format, without relative amplitudes.", fn, n+1).warn;
			format("Please see the FonaDyn 3.1 Release Notes for more information.").warn;
		});
	}

	saveClusterSettings { | path |
		var cDelim = VRPMain.cListSeparator;
		var dim = centroids[0].size;

		if (path.endsWith(".csv").not) {
			path = path ++ "_cEGG.csv";
		};
		File.use(path, "w", { | file |
			centroids.size do: { |k|
				file << pointsInCluster[k].asInteger;
				file.put(cDelim);
				centroids[k] do: { | value, i |
					file << value;
					if (i < (dim - 1), {file.put(cDelim)} );
				};
				file.put($\r); file.nl;
			}
		});
		filePath = path;
		("Saved" + path).postln;
	}

}