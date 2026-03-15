// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
VRPDataCluster {
	/**
	 * Fetching cluster data as:
	 * pointsInCluster = [# of points in cluster 1..nClusters]
	 * centroids = [ Centroid 1..nClusters ]
	 * where each Centroid is defined as an array of length nDimensions (the center of the cluster).
	 */
	var <>pointsInCluster;
	var <>centroids;
	var nClusters;
	var <>cycleData; // waveform from SmoothedClusterCycle
	var <>resetNow; // If true it will reset the counts/centroids on the next possible chance.
	classvar <csvSuffix;

	*new { | settings |
		^super.new.init(settings);
	}

	*initClass {
		csvSuffix = Dictionary.newFrom([\OldEGGcsvSuffix, "_clusters.csv", \EGGcsvSuffix, "_cEGG.csv"]);
	}

	*testSuffix { | fName |
		^(fName.toLower.endsWith(csvSuffix[\EGGcsvSuffix].toLower)
			or: fName.toLower.endsWith(csvSuffix[\OldEGGcsvSuffix].toLower))
	}

	init { | settings |
		nClusters = if(settings.isNil,
			{2}, 	// invoked by VRPViewClusters.loadClustersDialog, will be changed soon
			{settings.cluster.nClusters}
		);

		resetNow = false;
	}

	reset { | old |
		pointsInCluster = old.pointsInCluster;
		centroids = old.centroids;
		cycleData = old.cycleData;
	}

	nClusters {
		^pointsInCluster.size
	}

}
