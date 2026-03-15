// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
VRPDataClusterPhon {
	/**
	 * Fetching phonation type cluster data as:
	 * pointsInCluster = [# of points in cluster 1..nClusters]
	 * centroids = [ Centroid 1..nClusters ]
	 * where each Centroid is defined as an array of length nDimensions (the center of the cluster).
	 */

	var <>pointsInCluster;	// point counts returned by the server
	var <>centroids;		// centroids returned by the server
	var <>resetNow; 		// If true it will reset the counts/centroids on the next possible chance.
	classvar <csvSuffix;

	*new { | settings |
		^super.new.init(settings);
	}

	*initClass {
		csvSuffix = Dictionary.newFrom([\OldPhoncsvSuffix, "_phonclusters.csv", \PhoncsvSuffix, "_cPhon.csv"]);
	}

	*testSuffix { arg fName;
		^fName.toLower.endsWith(csvSuffix[\OldPhoncsvSuffix].toLower)
	    or: (fName.toLower.endsWith(csvSuffix[\PhoncsvSuffix].toLower));
	}

	init { | settings |
		resetNow = false;
		// csvSuffix = Dictionary.newFrom([\OldPhoncsvSuffix, "_phonclusters.csv", \PhoncsvSuffix, "_cphon.csv"]);
	}

	reset { | old |
		pointsInCluster = old.pointsInCluster;
		centroids = old.centroids;
	}

	nClusters {
		^pointsInCluster.size
	}

}
