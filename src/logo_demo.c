#include <pitrex/pitrexio-gpio.h>
#include <vectrex/vectrexInterface.h>

#include "../generated/logo_segments.h"

static void startFrame(void) {
  v_WaitRecal();
  v_setBrightness(96);
  v_readButtons();
  v_readJoystick1Analog();
}

static void drawLogo(void) {
  uint16_t i;

  for (i = 0; i < kLogoLineCount; ++i) {
    v_directDraw32(
      kLogoLines[i].x0,
      kLogoLines[i].y0,
      kLogoLines[i].x1,
      kLogoLines[i].y1,
      kLogoLines[i].brightness
    );
  }
}

int main(int argc, char **argv) {
  (void)argc;
  (void)argv;

  vectrexinit(1);
  v_setName("yt_logo");
  v_init();
  v_setRefresh(60);

  for (;;) {
    startFrame();
    drawLogo();
  }

  return 0;
}
