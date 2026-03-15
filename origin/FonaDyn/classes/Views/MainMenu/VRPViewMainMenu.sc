// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //

VRPViewMainMenu {
	var mView;

	var mViewGeneral;
	var mVRPViewGeneral;

	var mViewInput;
	var mVRPViewInput;

	var mViewOutput;
	var mVRPViewOutput;

	*new { | view |
		^super.new.init(view);
	}

	init { | view |
		var b = view.bounds;
		mView = view;

		// Init composite views
		mViewGeneral = CompositeView(mView, mView.bounds);
		mViewInput = CompositeView(mView, mView.bounds);
		mViewOutput = CompositeView(mView, mView.bounds);

		// Set the layout to let the children know their sizes
		mView.layout = VLayout(
			[mViewGeneral, stretch: 1],
			[mViewInput, stretch: 1],
			[mViewOutput, stretch: 1]
		);
		mView.layout.margins_([0, 0, 0, 5]);

		// Init the VRPViews of the children
		mVRPViewGeneral = VRPViewMainMenuGeneral(mViewGeneral);
		mVRPViewInput = VRPViewMainMenuInput(mViewInput);
		mVRPViewOutput = VRPViewMainMenuOutput(mViewOutput);
	}

	toggleHeight {
		mViewGeneral.visible_(mViewGeneral.visible.not);
		mViewOutput.visible_(mViewOutput.visible.not);
	}

	start {
		mVRPViewInput.start;
	}

	pause {
		mVRPViewInput.pause;
	}

	compactHeight { | bOn |
		mViewGeneral.visible_(bOn.not);
		mViewOutput.visible_(bOn.not);
	}

	visible {
		^mViewOutput.visible
	}

	stash { | settings |
		// REPLACED BY CALLS TO STASH WITHIN ALL .fetch METHODS
		// [
		// 	mVRPViewInput,
		// 	mVRPViewGeneral,
		// 	mVRPViewOutput
		// ]
		// do: { | v |
		// 	v.stash(settings);
		// };
		nil
	}

	fetch { | settings |
		[
			mVRPViewInput,  // First, because it parses scripts
			mVRPViewGeneral,
			mVRPViewOutput
		]
		do: { | v |
			v.fetch(settings);
		};
	}

	updateData { | data |
		[
			mVRPViewGeneral,
			mVRPViewInput,
			mVRPViewOutput
		]
		do: { | v |
			v.updateData(data);
		};
	}

	close {
		[
			mVRPViewGeneral,
			mVRPViewInput,
			mVRPViewOutput
		]
		do: { | v |
			v.close();
		};
	}
}