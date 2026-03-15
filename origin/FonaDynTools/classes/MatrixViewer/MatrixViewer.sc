// Copyright (C) 2016-2026 by Sten Ternström, KTH Stockholm
// Released under European Union Public License v1.2, at https://eupl.eu
// *** EUPL *** //
MatrixViewer {
	var mUV;
	var mGrid;
	var mMatrix; // The matrix to draw
	var mPalette; // Palette for the matrix values

	*new { | parent, grid |
		^super.new.init(parent, grid);
	}

	init { | parent, grid |
		mGrid = grid;

		mUV = UserView(parent, parent.bounds.moveTo(0, 0))
		.drawFunc_{
			var b = mUV.bounds;
			if ( mGrid.notNil, {
				mGrid.bounds_(b.moveTo(0, 0));
				mGrid.draw;
			});

			if (mMatrix.notNil and: mPalette.notNil, {
				var h = mMatrix.size;
				var w = mMatrix.first.size;
				var xstride = b.width / w;
				var ystride = b.height / h;
				var rect = Rect(0, 0, xstride, ystride);

				// Draw all rects
				Pen.use {
					mMatrix reverseDo: { | row, y |
						var py = ystride * y;
						var prow = mPalette[h - y - 1];
						rect.top = py;
						row do: { | value, x |
							if (value.notNil, {
								rect.left = xstride * x;
								Pen.color = prow[x];
								Pen.fillRect(rect);
							});
						};
					};
				};
			});
		};
	}

	view { ^mUV; }

	update { | matrix, palette |
		mMatrix = matrix.deepCopy;

		mPalette =
		mMatrix collect: { | row |
			row collect: { | value |
				if (value.notNil, { palette.(value) }, nil)
			}
		};

		mUV.refresh;
	}
}