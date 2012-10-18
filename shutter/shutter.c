/*
Copyright (c) 2012, Broadcom Europe Ltd
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of the copyright holder nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

// A simple demo using dispmanx to display an overlay

#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <assert.h>
#include <unistd.h>
#include <sys/time.h>

#include "bcm_host.h"

//#define WIDTH   200
//#define HEIGHT  200

#define ALIGN_UP(x,y)  ((x + (y)-1) & ~((y)-1))

typedef struct
{
    DISPMANX_DISPLAY_HANDLE_T   display;
    DISPMANX_MODEINFO_T         info;
    void                       *image;
    DISPMANX_UPDATE_HANDLE_T    update;
    DISPMANX_RESOURCE_HANDLE_T  resource;
    DISPMANX_ELEMENT_HANDLE_T   element;
    uint32_t                    vc_image_ptr;
    int				connected;

} RECT_VARS_T;

static RECT_VARS_T  gRectVars;
static VC_RECT_T       src_rect;
static VC_RECT_T       dst_rect;
static VC_IMAGE_TYPE_T type = VC_IMAGE_RGB565;


static void FillRect( VC_IMAGE_TYPE_T type, void *image, int pitch, int aligned_height, int x, int y, int w, int h, int val )
{
    int         row;
    int         col;

    uint16_t *line = (uint16_t *)image + y * (pitch>>1) + x;

    for ( row = 0; row < h; row++ )
    {
        for ( col = 0; col < w; col++ )
        {
            line[col] = val;
        }
        line += (pitch>>1);
    }
}

static VC_DISPMANX_ALPHA_T alpha = { DISPMANX_FLAGS_ALPHA_FROM_SOURCE | DISPMANX_FLAGS_ALPHA_FIXED_ALL_PIXELS, 
                             0, /*alpha 0->255*/
                             0 };

float totalTime = .4; //sec

float delay = 2; // totalTime/2;
float step = .05 / 128; // ((totalTime-delay)/2)/256;
//float step = .05 / 256; // ((totalTime-delay)/2)/256;

void hard_out(RECT_VARS_T *vars, int color);
void hard_in(RECT_VARS_T *vars);
void fade_out(RECT_VARS_T *vars, int color);
void fade_in(RECT_VARS_T *vars);
void disconnect(RECT_VARS_T *vars);

int main(int argc, char**argv)
{
    RECT_VARS_T    *vars;

    

    vars = &gRectVars;
    vars->connected = 0;

    bcm_host_init();



//forever:
//  read line
//  parse command
//     case  fade-to-black:
//	     open-display
//           create frame(black)
//           decrease transparency (opacity) till we have solid color
//           write ack
//     case  fade-to-white:
//	     open-display
//           create frame(white)
//           decrease transparency (opacity) till we have solid color
//           write ack
//     case  fade-in:
//           increase transparency (opacity) till we have full transparency
//           delete frame
//           close display
//           write ack





    int nbuf = 100;
    char *buf = (char*)malloc(sizeof(char)*nbuf);
   

    for(;;) {
        char *s = fgets(buf, nbuf, stdin);
	if (s == NULL && feof(stdin))
		break;

	if (strncmp(s, "fade-in", strlen("fade-in")) == 0) {
		fade_in(vars);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "fade-to-white", strlen("fade-to-white")) == 0) {
		int color = 0xFFFF; //white
		fade_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "fade-to-black", strlen("fade-to-black")) == 0) {
		int color = 0x0000; // black
		fade_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "hard-in", strlen("hard-in")) == 0) {
		hard_in(vars);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "hard-to-white", strlen("hard-to-white")) == 0) {
		int color = 0xFFFF; //white
		hard_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	} else if (strncmp(s, "hard-to-black", strlen("hard-to-black")) == 0) {
		int color = 0x0000; // black
		hard_out(vars, color);
		fprintf(stdout, "done\n");
		fflush(stdout);
	}
    }

    if(vars->connected)
        disconnect(vars);
    return 0;
}

void create_overlay(RECT_VARS_T *vars, int color)
{
    uint32_t        screen = 0;
    int             ret;

    if (vars->connected) {
	fprintf(stderr, "aldready connected, not creating overlay again\n");
	return;
    }
    //printf("Open display[%i]...\n", screen );
    vars->display = vc_dispmanx_display_open( screen );

    ret = vc_dispmanx_display_get_info( vars->display, &vars->info);
    assert(ret == 0);
    //printf( "Display is %d x %d\n", vars->info.width, vars->info.height );


    int width = vars->info.width, height = vars->info.height;
    int pitch = ALIGN_UP(width*2, 32);
    int aligned_height = ALIGN_UP(height, 16);

    vars->image = calloc( 1, pitch * height );
    assert(vars->image);

    FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      color);
    //FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      0x0000 );
    //FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      0xFFFF );
    //FillRect( type, vars->image, pitch, aligned_height,  0,  0, width,      height,      0xF800 );
    //FillRect( type, vars->image, pitch, aligned_height, 20, 20, width - 40, height - 40, 0x07E0 );
    //FillRect( type, vars->image, pitch, aligned_height, 40, 40, width - 80, height - 80, 0x001F );

    vars->resource = vc_dispmanx_resource_create( type,
                                                  width,
                                                  height,
                                                  &vars->vc_image_ptr );
    assert( vars->resource );
    vc_dispmanx_rect_set( &dst_rect, 0, 0, width, height);
    ret = vc_dispmanx_resource_write_data(  vars->resource,
                                            type,
                                            pitch,
                                            vars->image,
                                            &dst_rect );
    assert( ret == 0 );
    vars->update = vc_dispmanx_update_start( 10 );
    assert( vars->update );

    vc_dispmanx_rect_set( &src_rect, 0, 0, width << 16, height << 16 );

    vc_dispmanx_rect_set( &dst_rect, ( vars->info.width - width ) / 2,
                                     ( vars->info.height - height ) / 2,
                                     width,
                                     height );

    vars->element = vc_dispmanx_element_add(    vars->update,
                                                vars->display,
                                                2500,               // layer
                                                &dst_rect,
                                                vars->resource,
                                                &src_rect,
                                                DISPMANX_PROTECTION_NONE,
                                                &alpha,
                                                NULL,             // clamp
                                                VC_IMAGE_ROT0 );

    ret = vc_dispmanx_update_submit_sync( vars->update );
    assert( ret == 0 );

}


void hard_out(RECT_VARS_T *vars, int color)
{
    if (vars->connected) {
	fprintf(stderr, "aldready connected, not hard cut out again\n");
	return;
    }
    alpha.opacity = 255;
    create_overlay(vars, color);

    vars->connected  = 1;
}

void fade_out(RECT_VARS_T *vars, int color)
{
    int             ret;

    if (vars->connected) {
	fprintf(stderr, "aldready connected, not fading out again\n");
	return;
    }
    alpha.opacity = 0;
    create_overlay(vars, color);

    while(alpha.opacity < 254) {

        //printf( "%d %d Sleeping for 1 seconds...\n", i, alpha.opacity );
    	sleep( step );
    	alpha.opacity += 2;
	
        vars->update = vc_dispmanx_update_start( 10 );
        assert( vars->update );
    	vc_dispmanx_element_change_attributes( vars->update,
					   vars->element,
					   (1<<1),
					   2500,
                                           alpha.opacity,
                                                &dst_rect,
                                                &src_rect,
                                                vars->resource,
                                                VC_IMAGE_ROT0 );
    	ret = vc_dispmanx_update_submit_sync( vars->update );
    	assert( ret == 0 );
    }

    vars->connected  = 1;
}

void hard_in(RECT_VARS_T *vars)
{
    if (!vars->connected) {
	fprintf(stderr, "not connected, not hard cut in\n");
	return;
    }
    disconnect(vars);
}

void fade_in(RECT_VARS_T *vars)
{
    int             ret;

    if (!vars->connected) {
	fprintf(stderr, "not connected, not fading in\n");
	return;
    }
    while(alpha.opacity > 1) {

        //printf( "%d %d Sleeping for 1 seconds...\n", i, alpha.opacity );
    	sleep( step );
    	alpha.opacity -= 2;
	
        vars->update = vc_dispmanx_update_start( 10 );
        assert( vars->update );
    	vc_dispmanx_element_change_attributes( vars->update,
					   vars->element,
					   (1<<1),
					   2500,
                                           alpha.opacity,
                                                &dst_rect,
                                                &src_rect,
                                                vars->resource,
                                                VC_IMAGE_ROT0 );
    	ret = vc_dispmanx_update_submit_sync( vars->update );
    	assert( ret == 0 );
    }
    disconnect(vars);
}

void disconnect(RECT_VARS_T *vars)
{
    int             ret;

    if (!vars->connected) {
	fprintf(stderr, "not connected, not disconnecting\n");
	return;
    }
    vars->update = vc_dispmanx_update_start( 10 );
    assert( vars->update );
    ret = vc_dispmanx_element_remove( vars->update, vars->element );
    assert( ret == 0 );
    ret = vc_dispmanx_update_submit_sync( vars->update );
    assert( ret == 0 );
    ret = vc_dispmanx_resource_delete( vars->resource );
    assert( ret == 0 );
    ret = vc_dispmanx_display_close( vars->display );
    assert( ret == 0 );

    free(vars->image);
    vars->image = 0;

    vars->connected = 0;
}

