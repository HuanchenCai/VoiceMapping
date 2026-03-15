// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //


// This is a wrapper class for an array of one or more VRPDataLayer objects.
// It encapsulates the case of cluster drawing in several layers


VRPDataClusterMap {
	var <cSelected;		// not yet used
	var <cCount;
	var subLayers;		// Array (0..nClusters) of VRPDataLayer
	var mPF;

	*new { arg height, width, iMetric, nClusters=nil, bDiffMap;
		^super.new.init(height, width, iMetric, nClusters, bDiffMap);
	}

	init { arg height, width, iMetric, nClusters, bDiffMap;
		// arg iMetric should be replaced with sym
		var layer, sym;

		cSelected = 0;
		cCount = nClusters;
		if (nClusters.notNil,  {
			subLayers = Array.fill(nClusters+1, nil);
			sym = VRPSettings.metrics[iMetric].class.symbol; 	// for backward compat.
			layer = VRPDataLayer.new(sym, bDiffMap, cSelected, nClusters);
			subLayers[0] = layer;
			mPF = layer.metric;
			(1..nClusters) do: { |c, i|
				subLayers[c] = VRPDataLayer.new(sym, bDiffMap, c, nClusters);
			};
		});
	}

	select { | nCluster=0 |
		if (nCluster >= 0 and: { nCluster <= cCount }, {
			cSelected = nCluster;
		});
	}

	setPalette { | fnPal |
		(1..cCount) do: {
			subLayers[cSelected].mapData.setPalette(fnPal);
		};
	}

	subLayer { | index=0 |
		^subLayers[index]
	}

	mapData { | cSel=0 |
		^subLayers[cSel].mapData;
	}

	metric { | cSel=0 |
		^subLayers[cSel].metric;
	}

	reorder { | newOrder |
		var tmpOrder, tmpArr, metricsArr;
		// To recolor, we need only change to the new order
		// and reset the per-cluster palettes
		if ((newOrder.class==Array) and: (newOrder.size + 1 == subLayers.size),
			{
				var bOK = true;
				newOrder.do { arg elem, i; if (elem.class != Integer, { bOK = false }) };
				if (bOK, {
					tmpOrder = [0] ++ (newOrder + 1);
					tmpArr = subLayers[tmpOrder];
					subLayers = tmpArr;
					subLayers.do { arg d, i;
						d.metric.setClusters(i, cCount);
						d.mapData.setPalette(d.metric.getPaletteFunc);
					};
					subLayers[0].mapData.renumber(newOrder);
				})
			}
		);
	}

	at { | row, col, index=0 |
		^subLayers[index].mapData.at(row, col)
	}

	atIndex { | idx |
		^subLayers[cSelected].mapData.atIndex(idx)
	}

	putCycles { | row, col, nCluster, nCycles, total |
		var val;
		// Set the density of the cluster
		if (nCluster > 0, {
			val = [100*nCycles/total, nCycles];
			subLayers[nCluster].mapData.put(row, col, val);
		});
	}

	setMaxCluster { | row, col, totalCycles |
		var percent;
		var best_cluster_idx;

		// Find which cluster has the most cycles
		best_cluster_idx = subLayers[1..].maxIndex ( { | layer, idx | (layer.mapData.at(row, col) ? [0, 0])[1] } );

		// Store the dominant cluster's number and dominance in layer 0
		percent = (subLayers[best_cluster_idx+1].mapData.at(row, col) ? [0, 0])[0];
		subLayers[0].mapData.put(row, col, [best_cluster_idx, percent]);
	}

	setDiffs{ arg target, reference;    // Both will be VRPClusterMaps
		var r, t, d, diffN, diffP, row, col;
		var count = target.cCount;

		// In layer 0, set the index of changed cells to the new cluster
		target.mapData(0).mValues do: { |v, i|
			row = v[0];
			col = v[1];
			t = target.at(row, col);
			r = reference.at(row, col);
			if (r.notNil /* and: { t.notNil } */, {
				diffN = t[0]-r[0];
				diffP = t[1];
				if (diffN != 0,
					{
					subLayers[0].mapData.put(row, col, [t[0], diffP]);
					}
				);
			});
		};

		// In the other layers, compute differences in both percentages and cycles
		(1..count) do: { | c |
			subLayers[c].mapData.setDiffs(target.mapData(c), reference.mapData(c));
		}
	}

	interpolateSmooth { arg source, densityMap, kernel;
		var count = source.cCount;

		(1..count) do: { | c |
			var thatDSM = source.mapData(c);
			subLayers[c].mapData.interpolateSmooth(thatDSM, kernel);
		};
		densityMap.mValues do: { | v, ix |
			var col = v[1];
			var row = v[0];
			this.setMaxCluster(row, col, v[2]);
			// this.setMaxCluster(row, col);
		};
	}

}