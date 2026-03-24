import Box from "@material-ui/core/Box";
import Button from "@material-ui/core/Button";
import Card from "@material-ui/core/Card";
import CardContent from "@material-ui/core/CardContent";
import CardHeader from "@material-ui/core/CardHeader";
import CircularProgress from "@material-ui/core/CircularProgress";
import Grid from "@material-ui/core/Grid";
import LinearProgress from "@material-ui/core/LinearProgress";
import { createStyles, WithStyles, withStyles } from "@material-ui/core/styles";
import Typography from "@material-ui/core/Typography";
import Chip from "@material-ui/core/Chip";
import FolderIcon from "@material-ui/icons/Folder";
import PauseIcon from "@material-ui/icons/Pause";
import PlayArrowIcon from "@material-ui/icons/PlayArrow";
import StopIcon from "@material-ui/icons/Stop";
import LayersIcon from "@material-ui/icons/Layers";
import ScheduleIcon from "@material-ui/icons/Schedule";
import PrintIcon from "@material-ui/icons/Print";
import nullthrows from "nullthrows";
import React from "react";
import { Link } from "react-router-dom";
import { withAPI, WithAPIProps } from "../api";
import { getPrinterDisplayName, renderTime, sleep } from "../utils";

const styles = (theme: any) =>
  createStyles({
    playButton: {
      padding: 12,
      borderRadius: 12,
      minWidth: 120,
    },
    playIcon: {
      height: 20,
      width: 20,
    },
    statsContainer: {
      padding: theme.spacing(3),
      background: theme.palette.type === 'dark' 
        ? 'linear-gradient(135deg, #1e293b 0%, #334155 100%)'
        : 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)',
      borderRadius: 16,
      marginBottom: theme.spacing(3),
    },
    statCard: {
      background: theme.palette.type === 'dark' ? '#0f172a' : '#ffffff',
      borderRadius: 12,
      padding: theme.spacing(2),
      textAlign: 'center',
      border: theme.palette.type === 'dark' 
        ? '1px solid #334155' 
        : '1px solid #e2e8f0',
      boxShadow: theme.palette.type === 'dark'
        ? '0 4px 6px -1px rgba(0, 0, 0, 0.3)'
        : '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
    },
    progressContainer: {
      padding: theme.spacing(3),
      background: theme.palette.type === 'dark' ? '#1e293b' : '#ffffff',
      borderRadius: 16,
      marginBottom: theme.spacing(3),
      border: theme.palette.type === 'dark' 
        ? '1px solid #334155' 
        : '1px solid #e2e8f0',
    },
    loadingContainer: {
      flexGrow: 1,
      padding: theme.spacing(4),
      textAlign: "center",
    },
    modernCard: {
      borderRadius: 20,
      background: theme.palette.type === 'dark' 
        ? 'linear-gradient(135deg, #1e293b 0%, #334155 100%)'
        : 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
      boxShadow: theme.palette.type === 'dark'
        ? '0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2)'
        : '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      border: 'none',
    },
    statusChip: {
      fontSize: '0.875rem',
      fontWeight: 600,
      borderRadius: 20,
      padding: theme.spacing(0.5, 2),
    },
    buttonGroup: {
      '& > *': {
        margin: theme.spacing(0.5),
        borderRadius: 12,
        textTransform: 'none',
        fontWeight: 600,
        minWidth: 100,
      },
    },
  });

type PrinterState =
  | "IDLE"
  | "STARTING_PRINT"
  | "PRINTING"
  | "PAUSED"
  | "CLOSED";

function toPrinterState(state: string): PrinterState {
  if (
    state !== "IDLE" &&
    state !== "STARTING_PRINT" &&
    state !== "PRINTING" &&
    state !== "PAUSED" &&
    state !== "CLOSED"
  ) {
    throw Error("Unknown printer state " + state);
  }
  return state;
}

export interface PrintStatusState {
  isLoading: boolean;
  data?: {
    state: PrinterState;
    selectedFile: string;
    progress: number;
    currentLayer?: number;
    layerCount?: number;
    printTimeSecs?: number;
    timeLeftSecs?: number;
  };
}

const WAIT_BEFORE_REFRESHING_STATUS_MS = 250;

class PrintStatus extends React.Component<
  WithStyles<typeof styles> & WithAPIProps,
  PrintStatusState
> {
  intervalID: number | undefined;

  state: PrintStatusState = {
    isLoading: true,
  };

  async _refresh(
    waitMs: number = WAIT_BEFORE_REFRESHING_STATUS_MS
  ): Promise<void> {
    await sleep(waitMs);
    const response = await this.props.api.printStatus();
    if (response) {
      this.setState({
        isLoading: false,
        data: {
          state: toPrinterState(response.state),
          progress: response.progress,
          selectedFile: response.selected_file,
          currentLayer: response.current_layer,
          layerCount: response.layer_count,
          printTimeSecs: response.print_time_secs,
          timeLeftSecs: response.time_left_secs,
        },
      });
    }
  }

  async componentDidMount(): Promise<void> {
    await this._refresh(0);
    this.intervalID = window.setInterval(
      async () => await this._refresh(0),
      60 * 1000
    );
  }

  componentWillUnmount() {
    window.clearInterval(this.intervalID);
  }

  _getStatusColor(state: PrinterState): "default" | "primary" | "secondary" {
    switch (state) {
      case "PRINTING": return "primary";
      case "PAUSED": return "secondary";
      case "STARTING_PRINT": return "secondary";
      default: return "default";
    }
  }

  _getStatusLabel(state: PrinterState): string {
    switch (state) {
      case "IDLE": return "Ready";
      case "STARTING_PRINT": return "Starting...";
      case "PRINTING": return "Printing";
      case "PAUSED": return "Paused";
      case "CLOSED": return "Offline";
      default: return state;
    }
  }

  _renderButtons(): React.ReactElement {
    const { classes } = this.props;
    const { state } = nullthrows(this.state.data);
    
    if (state === "CLOSED") {
      return <React.Fragment />;
    }

    if (state === "IDLE") {
      return (
        <Box display="flex" justifyContent="center" mt={2}>
          <Button
            variant="contained"
            color="primary"
            size="large"
            startIcon={<FolderIcon />}
            component={Link}
            to="/files"
            className={classes.playButton}
          >
            Select File to Print
          </Button>
        </Box>
      );
    }

    return (
      <Box display="flex" justifyContent="center" flexWrap="wrap" className={classes.buttonGroup}>
        <Button
          variant={state === "PAUSED" ? "contained" : "outlined"}
          color="primary"
          size="large"
          startIcon={<PlayArrowIcon className={classes.playIcon} />}
          onClick={async () => {
            await this.props.api.resumePrint();
            await this._refresh();
          }}
          disabled={state !== "PAUSED"}
          className={classes.playButton}
        >
          Resume
        </Button>
        <Button
          variant="outlined"
          color="primary"
          size="large"
          startIcon={<PauseIcon className={classes.playIcon} />}
          onClick={async () => {
            await this.props.api.pausePrint();
            await this._refresh();
          }}
          disabled={state === "PAUSED" || state === "STARTING_PRINT"}
          className={classes.playButton}
        >
          Pause
        </Button>
        <Button
          variant="outlined"
          color="secondary"
          size="large"
          startIcon={<StopIcon className={classes.playIcon} />}
          onClick={async () => {
            await this.props.api.cancelPrint();
            await this._refresh();
          }}
          className={classes.playButton}
        >
          Stop
        </Button>
      </Box>
    );
  }

  _renderContent(): React.ReactElement | null {
    const { classes } = this.props;

    if (this.state.isLoading) {
      return (
        <Box className={classes.loadingContainer}>
          <CircularProgress size={60} />
          <Typography variant="h6" style={{ marginTop: 16 }}>
            Connecting to printer...
          </Typography>
        </Box>
      );
    }

    const {
      currentLayer,
      layerCount,
      progress,
      selectedFile,
      state,
      timeLeftSecs,
    } = nullthrows(this.state.data);

    if (state === "IDLE" || state === "CLOSED") {
      return (
        <Box textAlign="center" py={4}>
          <Box mb={3}>
            <PrintIcon style={{ fontSize: 64, opacity: 0.6 }} />
          </Box>
          <Typography variant="h4" gutterBottom style={{ fontWeight: 600 }}>
            {state === "CLOSED" ? "Printer Offline" : "Ready to Print"}
          </Typography>
          <Typography variant="body1" color="textSecondary" paragraph>
            {state === "CLOSED" 
              ? "Check printer connection and power"
              : "Select a file to start your next 3D print"
            }
          </Typography>
          {this._renderButtons()}
        </Box>
      );
    }

    return (
      <React.Fragment>
        {/* Status Header */}
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={3}>
          <Box>
            <Typography variant="h5" style={{ fontWeight: 600, marginBottom: 4 }}>
              {selectedFile}
            </Typography>
            <Chip
              label={this._getStatusLabel(state)}
              color={this._getStatusColor(state)}
              icon={<PrintIcon />}
              className={classes.statusChip}
            />
          </Box>
        </Box>

        {/* Progress Section */}
        <Box className={classes.progressContainer}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h6" style={{ fontWeight: 600 }}>
              Progress
            </Typography>
            <Typography variant="h4" color="primary" style={{ fontWeight: 700 }}>
              {Math.round(progress)}%
            </Typography>
          </Box>
          <LinearProgress 
            variant="determinate" 
            value={progress} 
            style={{ 
              height: 12, 
              borderRadius: 6,
              marginBottom: 16
            }}
          />
          <Typography variant="body2" color="textSecondary" align="center">
            {selectedFile}
          </Typography>
        </Box>

        {/* Stats Grid */}
        <Box className={classes.statsContainer}>
          <Grid container spacing={3}>
            <Grid item xs={6}>
              <Box className={classes.statCard}>
                <ScheduleIcon color="primary" style={{ fontSize: 32, marginBottom: 8 }} />
                <Typography variant="h4" style={{ fontWeight: 700, marginBottom: 4 }}>
                  {renderTime(nullthrows(timeLeftSecs))}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Time Remaining
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6}>
              <Box className={classes.statCard}>
                <LayersIcon color="primary" style={{ fontSize: 32, marginBottom: 8 }} />
                <Typography variant="h4" style={{ fontWeight: 700, marginBottom: 4 }}>
                  {currentLayer}/{layerCount}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Current Layer
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Box>

        {this._renderButtons()}
      </React.Fragment>
    );
  }

  render(): React.ReactElement | null {
    const { classes } = this.props;
    const printerName = getPrinterDisplayName();
    
    return (
      <Card className={classes.modernCard} elevation={0}>
        <CardHeader
          title={
            <Box display="flex" alignItems="center">
              <PrintIcon style={{ marginRight: 12, fontSize: 32 }} />
              <Typography variant="h4" style={{ fontWeight: 700, marginBottom: 4 }}>
                Printer Dashboard
              </Typography>
            </Box>
          }
          subheader={
            printerName && (
              <Typography variant="subtitle1" color="textSecondary">
                {printerName}
              </Typography>
            )
          }
          style={{ paddingBottom: 16 }}
        />
        <CardContent style={{ paddingTop: 0 }}>
          {this._renderContent()}
        </CardContent>
      </Card>
    );
  }
}

export default withStyles(styles)(withAPI(PrintStatus));
