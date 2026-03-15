// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPDataLayer {
	var <>mapData;    // a DrawableSparseMatrix
	var <>metric;     // a VRPMetric

	layerSymbol {
		^metric.class.symbol;
	}

	*new { arg metricSymbol, bDiffMap=false, cluster=0, nClusters=2;
		^super.new.init(metricSymbol, bDiffMap, cluster, nClusters);
	}

	init { arg metricSymbol, bDiffMap, cSelected, nClusters;
		var palette;

		metric = VRPSettings.metricsDict[metricSymbol].deepCopy;

		if (metric.isNil, {
			format("Metric % not found", metricSymbol).error;
			^nil
		});

		metric.setDifferencing(bDiffMap);

		if ([\ClustersEGG, \ClustersPhon].includes(metricSymbol),
			{
				metric.setClusters(cSelected, nClusters);
			}
		);

		palette = metric.getPaletteFunc;
		// +1 because we want to include the upper limit
		mapData = DrawableSparseMatrix.new(VRPDataVRP.vrpHeight+1, VRPDataVRP.vrpWidth+1, palette);
	}

	interpolateSmooth { | srcLayer, densityMap, kernel |
		mapData.interpolateSmooth(srcLayer.mapData, kernel);
	}
}