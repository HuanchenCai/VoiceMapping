// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPDataVRP {
	var <layers; 		// Dictionary of VRPDataLayer's and VRPDataClusterMap's
	var <>maxDensity; 	// Largest value in the density matrix, or nil if no data exists
	var mBeforeColor, mNowColor;
	var <>underlapBack;  // map of regions that don't overlap, for DIFF map backgrounds

	// The most recent frequency, amplitude, clarity, eggValid, entropy and cluster measurements
	var <>currentFrequency;
	var <>currentAmplitude;
	var <>currentClarity;
	var <>currentEGGvalid;
	var <>currentEntropy;
	var <>currentCluster;
	var <>currentClusterPhon;

	var mLastPathName;
	var <isDifferenceMap;
	var <>mapsWidth;

	// CHANGING THESE LIMITS WILL WORK, BUT IT WILL MAKE THE FILES YOU SAVE NON-STANDARD,
	// AND MAYBE INCOMPATIBLE WITH OTHER INSTALLATIONS OF FONADYN. SO TREAD CAREFULLY.
	// CELL GRID RESOLUTIONS WITH NON-INTEGER DECIBELS AND SEMITONES ARE NOT SUPPORTED.
	classvar <nMinMIDI = 30;
	classvar <nMaxMIDI = 96;
	classvar <nMinSPL = 40;
	classvar <nMaxSPL = 120;
	classvar <vrpWidth;  // nMaxMIDI - nMinMIDI; // 1 cell per semitone
	classvar <vrpHeight; // nMaxSPL  - nMinSPL;  // 1 cell per dB


	classvar <mLastPath;
	classvar <bFixedAspectRatio = false;
	classvar <fixedAspectRatio = 0.0; // free aspect ratio
	classvar <cppStr;

	*new { | settings, bDiff=false |
		^super.new.init(settings, bDiff);
	}

	*testSuffix { arg fName;
		^fName.toLower.endsWith("_vrp.csv")
	}

	*testSuffixSmooth { arg fName;
		^fName.toLower.endsWith("_s_vrp.csv")
	}

	*configureSPLrange {arg singerMode;
		switch (singerMode,
			true,  { nMaxSPL = 140; VRPControllerIO.configureSampleFormat("int24") },
			false, { nMaxSPL = 120 },
			{ nil }
		);
	}


	//// bFixedAspectRatio is now redundant, but is kept for backward compatibility
	*configureAspectRatio { arg fixed;
		case
		{ fixed.isKindOf(Boolean) }
		{
			bFixedAspectRatio = fixed;
			fixedAspectRatio = if (fixed, 2.0, 0.0)
		}
		{ fixed.isKindOf(Number)  }
		{
			fixedAspectRatio = fixed.asFloat;
			bFixedAspectRatio = if (fixed == 0.0, false, true)
		}
		{ ^fixed }  // Neither: fixed was probably nil
		;
		format("Aspect ratio set to %", if (fixedAspectRatio != 0.0, fixedAspectRatio, "free")).postln;
	}

	initClusters { | h, w, iType, nClusters |
		"Deprecated method: VRPDataVRP.initClusters".warn;
		^VRPDataClusterMap.new(h, w, iType, nClusters);
	}

	initClusteredLayers { | height, width, iType, nClusters, bDiffMap |
		var h = height ? vrpHeight + 1;
		var w = width ? vrpWidth + 1;
		var tempClusterMap;
		if (nClusters < 2, { "Tried to allocate < 2 clusters for a map".error });
		case
		{ iType == VRPSettings.iClustersEGG  }
			{
			tempClusterMap  = VRPDataClusterMap.new(h, w, iType, nClusters, bDiffMap);
			layers.put(\ClustersEGG, tempClusterMap);
			}
		{ iType == VRPSettings.iClustersPhon }
			{
			tempClusterMap = VRPDataClusterMap.new(h, w, iType, nClusters, bDiffMap);
			layers.put(\ClustersPhon, tempClusterMap);
		};
	}

	init { | settings, bDiff |
		var a, w, h, nC;
		var mMetric;

		vrpWidth  = nMaxMIDI - nMinMIDI;
		vrpHeight = nMaxSPL  - nMinSPL;

		w = vrpWidth + 1;    // +1 because we want to include the upper limit
		h = vrpHeight + 1;

		// maxDensity = nil;
		layers = Dictionary();
		isDifferenceMap = bDiff;

		VRPSettings.metrics[0..VRPSettings.iLastMetric].do { | m |
			var sym = m.class.symbol;
			var l = VRPDataLayer.new(sym, isDifferenceMap);
			// Putting this as a switch statement
			// makes the ordering of Metrics flexible
			layers.put(sym, l);
		};

		this.initUnderlap;

		// Match "CCPs" or "CPP" depending on how the current FonaDyn was compiled
		cppStr = if (VRPSettings.metrics[VRPSettings.icppSmoothed].class.symbol == \CPPs, "CPPs", "CPP");

		// invoked by VRPViewVRP.loadVRPdataDialog, will be changed soon
		nC = if (settings.isNil, 2, { settings.cluster.nClusters });
		this.initClusteredLayers(h, w, VRPSettings.iClustersEGG, nC, isDifferenceMap);

		nC = if (settings.isNil, 2, { settings.clusterPhon.nClusters });
		this.initClusteredLayers(h, w, VRPSettings.iClustersPhon, nC, isDifferenceMap);

		mLastPath = thisProcess.platform.recordingsDir;
		mLastPathName = PathName("");
		mapsWidth = 1;
	} /* .init */

	initUnderlap {
		underlapBack = DrawableSparseMatrix.new(vrpHeight + 1, vrpWidth + 1, VRPMetric.fnPrePostPalette);
	}

	// .reset is used to retain the data from the previous run
	reset { | old |
		layers = old.layers;
		underlapBack = old.underlapBack;
	}

	*frequencyToIndex { arg freq, width = VRPDataVRP.vrpWidth;
		^freq
		.linlin(nMinMIDI, nMaxMIDI, 0, width)
		.round
		.asInteger;
	}

	*amplitudeToIndex { arg amp, height = VRPDataVRP.vrpHeight;
		^(amp + nMaxSPL)
		.linlin(nMinSPL, nMaxSPL, 0, height)
		.round
		.asInteger;
	}

	lastPathName { ^mLastPathName }

	lastPathName_ { | pathName |
		mLastPathName = PathName.new(pathName.fullPath.tr($\\, $/));
	}

	reorder { arg newOrder, metricID;
		switch ( metricID,
			VRPSettings.iClustersEGG,  { layers[\ClustersEGG].reorder(newOrder) },
			VRPSettings.iClustersPhon, { layers[\ClustersPhon].reorder(newOrder) }
		);
	}

	interpolateSmooth { arg dataSource, clarityThreshold=0.96, kernelCustom=nil;
		//// Impulse kernel: no smoothing!
		//// var kernelImpulse = [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]];
		//// Hamming window kernel
		//// var kernelHamming = [[0.444, 0.7071, 0.444], [0.7071, 1.0, 0.7071], [0.444, 0.7071, 0.444]];
		var kernelDefault = [[2, 5, 2], [5, 10, 5], [2, 5, 2]]; // Sharper kernel
		var kernel = kernelCustom ? kernelDefault;
		var density = layers[\Density].mapData;
		var destClarity, srcClarity = dataSource.layers[\Clarity].mapData;
		var fnThreshold = { arg val; if (val >= clarityThreshold, val, nil) };

		// First translate the Clarity layer, removing all sub-threshold cells
		destClarity = srcClarity.translate( fnThreshold );
		dataSource.layers[\Clarity].mapData = destClarity;

		// Now fill in the data - this takes a little time, so post the progress.
		"Smoothing: ".post;
		VRPSettings.metrics do: { | m, ix |
			var sym = m.class.symbol;
			var layer = layers[sym];

			layer.interpolateSmooth(dataSource.layers[sym], density, kernel);
			format(">% ", m.class.symbol).post;
			if (ix.mod(6) == 0, { "...".postln });
		};
		"...done!".postln;
	} /* .interpolateSmooth */

	saveVRPdata { | path, mapMode=nil |
		var cDelim = VRPMain.cListSeparator;
		var density = layers[\Density].mapData;
		var eggClusters, phonClusters, lr;
		var mostCommonClusterEGG = layers[\ClustersEGG].mapData(0);
		var mostCommonClusterPhon = layers[\ClustersPhon].mapData(0);

		var suffix = case
		{ mapMode == VRPViewVRP.iDiff   } { "_D_VRP.csv" }
		{ mapMode == VRPViewVRP.iSmooth } { "_S_VRP.csv" }
		{ "_VRP.csv" };
		if (path.toLower.endsWith(".csv").not) {
			path = path ++ suffix; // "VRP Save File"
		};
		this.lastPathName = PathName(path);

		lr = layers[\ClustersEGG];
		eggClusters = lr.cCount.collect { | ix | lr.mapData(ix+1) };
		lr = layers[\ClustersPhon];
		phonClusters = lr.cCount.collect { | ix | lr.mapData(ix+1) };

		// Write every non-nil VRP cell as a line
		// First cols are x,y in (MIDI, dB),
		// then single metrics, last cluster cycle-counts
		File.use(path, "w", { | file |
			var cv, m, cSyms;

			// Build and output the title row, using column headings from the metrics
			cv = List.newUsing(["MIDI", "dB"]);
			cSyms = List.new();

			VRPSettings.metrics[0..VRPSettings.iLastMetric] do: { |m|
				cv.add(m.csvName);
				cSyms.add(m.class.symbol);
			};
			cv.add("maxCluster");
			eggClusters.size.do ({ |i| cv = cv.add("Cluster"+(i+1).asString)});
			cv.add("maxCPhon");
			phonClusters.size.do ({ |i| cv = cv.add("cPhon"+(i+1).asString)});

			// All column headings are in place: output the first row
			cv.do ({|v, i|
				file << v;
				if (i < (cv.size-1), { file.put(cDelim)})
			});
			file.put($\r); file.nl;
			cv.clear;

			// Build and output the data rows
			// Cells below the clarity threshold are not stored
			density.rows.do({ |r|
				density.columns.do({arg c; var dValue, mc, lr;
					dValue = density.at(r, c);
					if (dValue.notNil, {
						// Cell coordinates and Total
						cv.add(c+nMinMIDI);
						cv.add(r+nMinSPL);
						cv.add(dValue);

						// Single-metric values
						cSyms[1..].do { | s, ix |
							cv.add(layers[s].mapData.at(r,c));
						};

						// EGG cluster data
						mc = mostCommonClusterEGG.at(r, c);
						if (mc.isNil, { cv.add(-1) }, { cv.add(1 + mc[0]) });
						eggClusters.size.do ({|k| cv = cv.add( (eggClusters[k].at(r, c) ? [0,0])[1] ) } );

						// Phontype cluster data
						mc = mostCommonClusterPhon.at(r, c);
						if (mc.isNil, { cv.add(-1) }, { cv.add(1 + mc[0]) });
						phonClusters.size.do ({|k| cv = cv.add( (phonClusters[k].at(r, c) ? [0,0])[1] ) } );

						// The case statement assumes fixed metricNumber == i
						cv.do ({|v, i|
							// Avoid saving a silly excess of decimals to the _VRP file
							case
							// Columns MIDI, dB
							{ i < 2 }  { file << v }
							// Empty columns print as "nil"
							{ v.isNil } { file << v }
							// Total cycles can be non-integer, but only in smoothed maps
							{ i == 2 } { if (v.frac != 0.0, { file << v.round(0.01) }, { file << v } ) }
							// Columns with metric averages
							{ (i-2) < VRPSettings.iClustersEGG } { file << v.round(VRPSettings.metrics[i-2].csvPrecision) }
							// Column maxCluster
							{ i == (VRPSettings.iClustersEGG + 2) } { file << v }
							// Column maxCPhon
							{ i == (VRPSettings.iClustersPhon + 2 + eggClusters.size) } { file << v }

							// case ELSE: Columns Cluster_n or cPhon_n with cycle counts
							// These can be non-integer, if the map was smoothed
							{ if (v.frac != 0.0, { file << v.round(0.01) }, { file << v } ) }
							; /* case */

							if (i < (cv.size-1), { file.put(cDelim)});
						});

						file.put($\r); file.nl;
						cv.clear;
				})}
		)})});
		("Saved" + path).postln;
	} /* saveVRPdata{} */

	////////////////////////////////////////////////////////////////////////////////
	// loadVRPdata returns the number of clusters found in the _VRP.CSV file,
	// or -1 if there is a file access error. The number of existing clusters must match.
	////////////////////////////////////////////////////////////////////////////////

	loadVRPdata { | path |
		var cDelim = VRPMain.cListSeparator;
		var nClustersEGG = 0;
		var nClustersPhon = 0;
		var nCols = 0, dBcol=1;
		var ixListEGG, ixListPhon;
		var cSyms = List.new();

		VRPSettings.metrics[0..VRPSettings.iLastMetric] do: { |m|
			cSyms.add(m.class.symbol);
		};

		block { |break|
			if (path.toLower.endsWith("_vrp.csv"), {
				var cArray=nil, cNum, cIx;
				var testItem, ct, ixEGG, ixPhon;
				mLastPathName = PathName.new(path);
				mLastPath = mLastPathName.pathOnly;

				if (File.exists(path).not, {
					format("Could not find file: %", path.quote).error;
					break.value(-1);
				});

				cArray = FileReader.read(path, skipEmptyLines: true, skipBlanks: true, delimiter: cDelim);

				// If the first row contains only one element, it might be comma-delimited (not semicolon).
				// Try to parse it as such. This saves hassle when reading CSV files from elsewhere.
				if (cArray[0].size == 1, {
					cArray.clear;
					cArray = FileReader.read(path, skipEmptyLines: true, skipBlanks: true, delimiter: $,);
				});

				if (cArray.isNil, { nClustersEGG = -1; nClustersPhon = -1 }, {
					// Remove trailing empty cells caused by delimiter(s) at the end of a line
					cArray do: { | row, ix | while { row.last.isEmpty } { row.pop } };

					// First cols are x,y in (MIDI, dB),
					// then in order as defined in VRPSettings.metrics

					ct = cArray.at(0); 					// copies the row of column headings

					// If we are not in "singer mode", check if the map contains SPLs > 120.
					// If so, tell the user to reconfigure and restart
					if (VRPDataVRP.nMaxSPL < 140, {
						var aLevels;
						dBcol = ct.indexOfEqual("dB");
						aLevels = cArray[1..].collect { arg nStr, ix; cArray[ix][dBcol].asFloat };
						if (aLevels.indexOfGreaterThan(120.0).notNil, {
							"This map file contains SPLs higher than 120 dB.".error;
							"Please modify the startup file; see handbook section 3.3.".warn;
							break.value(-2);
						});
					});

					nCols = cArray[1].size;

					// Find all EGG-cluster columns, even if they are not in order
					ixListEGG = [ct.indexOfEqual("maxCluster")];
					cNum = 1;
					cIx = ct.indexOfEqual("Cluster"+cNum);
					while
					{ cIx.notNil }
					{
						ixListEGG = ixListEGG.add(cIx);
						cNum = cNum+1;
						cIx = ct.indexOfEqual("Cluster"+cNum);
					};
					nClustersEGG = if (ixListEGG[0].isNil, { 2 }, { ixListEGG.size - 1 });

					// Find all phon-cluster columns, even if they are not in order
					ixListPhon = [ct.indexOfEqual("maxCPhon")];
					nClustersPhon = if (ixListPhon[0].isNil, 2,
						{
							cNum = 1;
							cIx = ct.indexOfEqual("cPhon"+cNum);
							while
							{ cIx.notNil }
							{
								ixListPhon = ixListPhon.add(cIx);
								cNum = cNum+1;
								cIx = ct.indexOfEqual("cPhon"+cNum);
							};
							(ixListPhon.size - 1)
						}
					);

					// Delete the row of column headings
					cArray.removeAt(0);

					// In case nClusters has changed, we must reallocate "clusters" and change palettes
					this.initClusteredLayers(vrpHeight+1, vrpWidth+1, VRPSettings.iClustersEGG, nClustersEGG, false);
					this.initClusteredLayers(vrpHeight+1, vrpWidth+1, VRPSettings.iClustersPhon, nClustersPhon, false);

					/* Parse cArray row by row */
					cArray.do( { | rowData, rowNo |
						var x, y, value, totalCycles, mostCycles, ix;

						x = rowData[ct.indexOfEqual("MIDI")].asInteger - nMinMIDI;
						y = rowData[ct.indexOfEqual("dB")].asInteger - nMinSPL;
						totalCycles = rowData[ct.indexOfEqual("Total")].asFloat;

						cSyms.do { | s, j |
							var lr = layers[s];
							var ix = ct.indexOfEqual(lr.metric.csvName);
							if (ix.notNil, {
								// Skip cells flagged as empty by FonaDyn or by Matlab
								if ((rowData[ix] != "nil") and: { rowData[ix] != "NaN" }, {
									lr.mapData.put(y, x, rowData[ix].asFloat);
								})
							});
						};

						// why should "maxCluster" column be mandatory?

						if (ixListEGG[0].notNil, {
							ixListEGG[1..].do { | ixEGG, i |
								value = rowData[ixEGG].asFloat;
								if (value > 0, { layers[\ClustersEGG].putCycles(y, x, i+1, value, totalCycles) });
							};
							layers[\ClustersEGG].setMaxCluster(y, x, totalCycles);
						});

						// fill in phontype cluster data, if present
						if (ixListPhon[0].notNil, {
							ixListPhon[1..].do { | ixPhon, i |
								value = rowData[ixPhon].asFloat;
								if (value > 0, { layers[\ClustersPhon].putCycles(y, x, i+1, value, totalCycles) });
							};
							layers[\ClustersPhon].setMaxCluster(y, x, totalCycles);
						});

					})
				});

				format("    Loaded %\n  with % EGG clusters and % phonation type clusters",
						path, nClustersEGG, nClustersPhon).postln;
			});
			^nClustersEGG
		}
		^nClustersEGG
	} /* loadVRPdata{} */
}
