// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

// There is only one VRPDataPlayer object: VRPData.player .
// It is a data-exchange and handshaking "center"
// through which several views (VRPViewVRP, VRPViewPlayer, VRPViewPlots and VRPViewMain)
// can communicate about map-playback within their .updateData handlers.

VRPDataPlayer {
	// States
	classvar <enabled = false;
	var <status;
	var <available = 0;   // set to > 0 by VRPViewPlayer if playing is possible
	var bMouseDown, bPlayNow, bStopNow, bMaxed;
	var <>cond;

	// Constants
	classvar <iEmptyCell = -2;
	classvar <iAnyCell = -1;
	classvar <iStatusIdle = 0;
	classvar <iStatusPending = 1;
	classvar <iStatusProcessing = 2;
	classvar <iStatusWaitingForMouseUp = 3;
	classvar <defaultMidiTol = 0.75;		// +/- semitones
	classvar <defaultLevelTol = 0.75;		// +/- dB

	// Variables
	var <vrpViewSignal; 			// The VRPViewPlayer object for the signal, or nil
	var ptMouseCell;
	var clusterTarget;
	var clusterType;
	var eggClusterData;
	var eggFDs;
	var ixEggFDs;
	var midiTol, levelTol;
	var <scaleTolerance;
	var <>representativity;		// 0...1
	var iSelectionBeingPlayed;  // 0: not playing; >0 selection number
	var <>signalDSM;			// DrawableSparseMatrix from the selection, if any
	var <>targetDSM;			// DrawableSparseMatrix from the Before-target, if any

	*new { | settings |
		^super.new.init(settings);
	}

	*configureMapPlayer { arg bEnable;
		if (bEnable.notNil, {
			enabled = bEnable
		});
	}

	init { | settings |
		bMaxed = false;
		ptMouseCell = 0@0;
		clusterTarget = iEmptyCell;
		clusterType = VRPSettings.iClustersEGG;
		eggFDs = [];
		ixEggFDs = -1;
		status = iStatusIdle;
		representativity = 0.0;
		bMouseDown = false;
		bPlayNow = false;
		bStopNow = false;
		midiTol = defaultMidiTol;
		levelTol = defaultLevelTol;
		scaleTolerance = 1.0;
		iSelectionBeingPlayed = 0;
		signalDSM = nil;
		cond = Condition.new(false);
		vrpViewSignal = nil;
		// this.inspect();
	}

	midiTolerance {
		^midiTol * scaleTolerance;
	}

	levelTolerance {
		^levelTol * scaleTolerance;
	}

	setMaxReached { arg maxed;
		bMaxed = maxed;
	}

	setSelectionPlaying { arg n;
		iSelectionBeingPlayed = n;
	}

	getSelectionPlaying {
		^iSelectionBeingPlayed;
	}

	requestScaling { arg scaleRequested;
		if (bMaxed and: (scaleRequested > scaleTolerance), {
			"Can't play more than 63 segments".warn;
		}, {
			scaleTolerance = scaleRequested
		});
		^scaleTolerance;
	}

	markForListening { arg ptCell, target, cType, bShift;
		if (enabled and: (available > 0) and: (status == iStatusIdle), {
			bMouseDown = true;
			bPlayNow = bShift;
			iSelectionBeingPlayed = 0;
			bStopNow = false;
			ptMouseCell = ptCell;
			ptMouseCell.y = ptCell.y - VRPDataVRP.nMaxSPL;
			clusterTarget = target;
			clusterType = cType;
			if (target == iEmptyCell, {
				ptMouseCell = 0@0; // this invokes a clearing of the selections (pt not found)
			});
			status = iStatusPending;
			cond.test = false;
			// format("markForListening: %, cluster: %, type: %", status, target, clusterType).postln;
		});
	}

	markForReplay {
		if (status == iStatusIdle, {
			bPlayNow = true;
			status = iStatusPending;
			cond.test = false;
			// format("markForReplay: %", status).postln
		});
	}

	markForStop {
		if (status == iStatusProcessing, {
			bPlayNow = false;
			bStopNow = true;
			cond.test = true;
			cond.signal;
			// format("markForStop: %", status).postln
		});
	}

	markAsHandled {
		if (bMouseDown, { status = iStatusWaitingForMouseUp }, { status = iStatusIdle });
		bPlayNow = false;
		bStopNow = false;
		// format("markAsHandled: %", status).postln
	}

	markMouseUp {
		bMouseDown = false;
		if (status == iStatusWaitingForMouseUp, {
			status = iStatusIdle
		});
		// format("markMouseUp: %", status).postln
	}

	markAsBusy {
		status = iStatusProcessing;
		// format("markAsBusy: %", status).postln
	}

	setTolerance { arg tolMidi, tolLevel;
		".setTolerance called in error".warn;
		midiTol = tolMidi;
		levelTol = tolLevel;
	}

	setAvailable { arg iAvailable;
		available = iAvailable;
		// format("data.player.available set to %", available).postln;
	}

	setEggFDs { arg ix, arrayFDs;		// Pass an empty array to clear contents
		eggFDs = arrayFDs;
		ixEggFDs = ix;
	}

	setVRPView { | vrpView |
		vrpViewSignal = vrpView ;
	}

	getEggFDs {
		^eggFDs ++ ixEggFDs;
	}

	idle {
		^status == iStatusIdle;
	}

	pending {
		^status == iStatusPending;
	}

	playNow {
		^bPlayNow;
	}

	stopNow {
		^bStopNow;
	}

	busy {
		^status >= iStatusProcessing
	}

	target {
		var pt = ptMouseCell ? Point();
		^[pt, clusterTarget, clusterType]
	}

}