// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewCycleDetectionData {

	// Views only the EGG signal
	*egg { | name, frame_first = 0, frame_count = 2000 |
		VRPViewCycleDetectionData
		.internal_do_view(name, frame_first, frame_count, [0]);
	}

	// Views only the cycle markers
	*cycle_markers { | name, frame_first = 0, frame_count = 2000 |
		VRPViewCycleDetectionData
		.internal_do_view(name, frame_first, frame_count, [1]);
	}

	// Superposes the cycle markers over the actual EGG signal
	*both { | name, frame_first = 0, frame_count = 2000 |
		VRPViewCycleDetectionData
		.internal_do_view(name, frame_first, frame_count, [0, 1]);
	}

	// Internal helper function for egg, cycle_markers and both.
	*internal_do_view { | name, frame_first, frame_count, channels |
		var path;
		path = thisProcess.platform.recordingsDir +/+ name ++ ".wav";

		// NOTE: The plot is actually quite buggy with the cycle detection trigger data, so a small window is suitable to watch.
		Buffer.readChannel(Server.default, path, frame_first, frame_count, channels, { | buf |
			{
				buf.plot.superpose_(true)
			}.defer;
		});
	}
}