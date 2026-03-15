// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
SmoothedClusterCycle : UGen {
	*allocBuffer { | server, nClusters, nSamples |
		^Buffer.alloc(server, nClusters * (nSamples + 2));
	}

	*splitData { | data, nClusters, nSamples |
		var ret = [nil, nil, nil];
		var pos = data.size - (2 * nClusters);
		var end = pos + nClusters;
		ret[0] = data.copyFromStart(pos-1).unlace(nClusters, nSamples);
		ret[1] = data.copyRange(pos, end-1);
		ret[2] = data.copyToEnd(end);
		^ret;
	}

	*getCycleData { | data, index, nClusters, nSamples |
		var ret = this.getCycleDataRange(data, index, nClusters, nSamples);
		var range = ret[0];
		ret[0] = data.copyRange(range[0], range[1]);
		^ret;
	}

	*getCycleDataRange { | data, index, nClusters, nSamples |
		var ret = [nil, nil, nil];
		var sqerror_base = data.size - (2 * (nClusters - index));
		ret[2] = data[ sqerror_base + 1 ]; //
		ret[1] = data[ sqerror_base ];
		ret[0] = Array.with(index * nSamples, (index+1) * nSamples - 1);
		^ret;
	}

	*ar { | bufnum, in, gateCycle, gateFilteredDFT, clusterNumber, nClusters, minSamples = 10, maxSamples = 882, smoothFactor = 0.99 |
		^this.multiNew('audio', bufnum, in, gateCycle, gateFilteredDFT, clusterNumber, nClusters, minSamples, maxSamples, smoothFactor);
	}
}