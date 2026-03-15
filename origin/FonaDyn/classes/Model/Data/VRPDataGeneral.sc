// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
// Copyright (C) 2016-2025 by Sten Ternström & Dennis J. Johansson, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPDataGeneral {
	var <timestamp; // Timestamp as YYMMDD_HHMMSS

	var <>error; // Error message to be presented - this message takes precedence over warning
	var <>warning; // Warning to be presented - this message takes precedence over notification
	var <>notification; // Notification to be presented - this message is only presented if no error or warning is present

	var <>stopping; // True if the server is stopping
	var <>starting; // True if the server is starting
	var <>started;  // True if the server IS started
	var <>aborted;  // True if a sanity check failed
	var <>pause;   /// Pause states: 0=not, 1=pausing, 2=paused, 3=resuming

	var <>enterTime, <>frameLoad;

	*new { | settings |
		^super.new.init(settings);
	}

	init { | settings |
		timestamp = Date.localtime.stamp;

		started = false;
		starting = false;
		stopping = false;
		aborted = false;

		pause = 0;

		error = nil;
		warning = nil;
		notification = nil;
		enterTime = Main.elapsedTime;
		frameLoad = 0.0;
	}

	idle {
		var tmp;
		tmp = stopping or: starting or: started or: (pause.asBoolean);
		^tmp.not;
	}

	reset { | old |
		started = old.started;
		starting = old.starting;
		stopping = old.stopping;
		pause = old.pause;

		error = old.error;
		warning = old.warning;
		notification = old.notification;
		enterTime = old.enterTime;
	}

	markTime {
	 	enterTime = Main.elapsedTime;
	}

	addTime { | scaler |
		frameLoad = scaler * (Main.elapsedTime - enterTime) ;
	}

}

