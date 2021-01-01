/*
 * Copyright 2020-2021 Hewlett Packard Enterprise Development LP
 * Copyright 2016-2019 Cray Inc.
 * Other additional copyright holders may be indicated within.
 *
 * The entirety of this work is licensed under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 *
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* Implementation of a "Multi-group", similar to a Tab set but without
 * the tabs.  Control of which group is visible is one of several methods
 *  that select the group to be displayed.
 */

#ifndef SELECTBROWSER_H
#define SELECTBROWSER_H

#include <FL/Fl_Browser.H>

// Allow a selection to last past the "FL_RELEASE" event

class SelectBrowser : public Fl_Browser {

  void *lastSelected;

  public:

  SelectBrowser (int x, int y, int w, int h, const char *l = 0);

  int handle(int event);

  void *lastSel (void) { return lastSelected; }

};


#endif
