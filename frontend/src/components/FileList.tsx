import Box from "@material-ui/core/Box";
import Card from "@material-ui/core/Card";
import CardContent from "@material-ui/core/CardContent";
import CardHeader from "@material-ui/core/CardHeader";
import CircularProgress from "@material-ui/core/CircularProgress";
import List from "@material-ui/core/List";
import ListItem from "@material-ui/core/ListItem";
import ListItemIcon from "@material-ui/core/ListItemIcon";
import ListItemText from "@material-ui/core/ListItemText";
import Typography from "@material-ui/core/Typography";
import { createStyles, WithStyles, withStyles } from "@material-ui/core/styles";
import FolderIcon from "@material-ui/icons/Folder";
import InsertDriveFileIcon from "@material-ui/icons/InsertDriveFile";
import LayersIcon from "@material-ui/icons/Layers";
import nullthrows from "nullthrows";
import React from "react";
import { useNavigate } from "react-router-dom";
import {
  DirectoryAPIResponse,
  FileAPIResponse,
  FileListAPIResponse,
  useAPI,
  withAPI,
  WithAPIProps,
} from "../api";
import { renderTime, sleep } from "../utils";
import FileDetailsDialog from "./FileDetailsDialog";
import UploadButton from "./UploadButton";

function DirectoryListItem({
  directory,
  onSelect,
  classes,
}: {
  directory: DirectoryAPIResponse;
  onSelect: (dirname: string) => void;
  classes?: any;
}): React.ReactElement {
  return (
    <React.Fragment>
      <ListItem
        button
        key={directory.dirname}
        onClick={() => onSelect(directory.dirname)}
        className={classes?.listItem}
        style={{ marginBottom: 8 }}
      >
        <ListItemIcon>
          <FolderIcon color="primary" />
        </ListItemIcon>
        <ListItemText 
          primary={
            <Typography variant="subtitle1" style={{ fontWeight: 600 }}>
              {directory.dirname}
            </Typography>
          }
          secondary="Folder"
        />
      </ListItem>
    </React.Fragment>
  );
}

function FileListItem({
  file,
  onDelete,
  classes,
}: {
  file: FileAPIResponse;
  onDelete: () => void;
  classes?: any;
}): React.ReactElement {
  const [open, setOpen] = React.useState(false);
  const handleClickOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  const printTime = file.print_time_secs
    ? renderTime(file.print_time_secs)
    : null;
  const navigate = useNavigate();
  const api = useAPI();
  return (
    <React.Fragment>
      <ListItem 
        button 
        key={file.filename} 
        onClick={handleClickOpen}
        className={classes?.listItem}
        style={{ marginBottom: 8 }}
      >
        <ListItemIcon>
          {file.can_be_printed ? 
            <LayersIcon color="primary" /> : 
            <InsertDriveFileIcon color="secondary" />
          }
        </ListItemIcon>
        <ListItemText 
          primary={
            <Typography variant="subtitle1" style={{ fontWeight: 600 }}>
              {file.filename}
            </Typography>
          }
          secondary={
            <Box>
              <Typography variant="body2" color="textSecondary">
                {file.can_be_printed ? '3D Print File' : 'File'}
              </Typography>
              {printTime && (
                <Typography variant="body2" color="textSecondary">
                  Print time: {printTime}
                </Typography>
              )}
            </Box>
          }
        />
      </ListItem>
      <FileDetailsDialog
        filename={file.filename}
        canBePrinted={file.can_be_printed}
        path={file.path}
        onCancel={handleClose}
        onClose={handleClose}
        onPrint={async () => {
          await api.startPrint(file.path);
          setOpen(false);
          navigate("/");
        }}
        onDelete={async () => {
          await api.deleteFile(file.path);
          setOpen(false);
          await onDelete();
        }}
        open={open}
        scroll="paper"
      />
    </React.Fragment>
  );
}

export interface FileListState {
  isLoading: boolean;
  path: string;
  data?: FileListAPIResponse;
}

const styles = (theme: any) =>
  createStyles({
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
    listItem: {
      borderRadius: 12,
      marginBottom: theme.spacing(1),
      background: theme.palette.type === 'dark' ? '#0f172a' : '#f8fafc',
      border: theme.palette.type === 'dark' 
        ? '1px solid #334155' 
        : '1px solid #e2e8f0',
      '&:hover': {
        background: theme.palette.type === 'dark' ? '#1e293b' : '#e2e8f0',
      },
    },
  });

class FileList extends React.Component<
  WithStyles & WithAPIProps,
  FileListState
> {
  state: FileListState = {
    isLoading: true,
    path: "",
  };

  async refresh(): Promise<void> {
    // FIXME: this is kind of nasty, it's just here because FileList sometimes
    // fails to render on storybook, which makes the storyshot tests for this
    // component fail when they run
    await sleep(0);
    const response = await this.props.api.listFiles(this.state.path);
    if (response) {
      this.setState({
        isLoading: false,
        data: response,
      });
    }
  }

  async componentDidMount(): Promise<void> {
    await this.refresh();
  }

  _renderContent(): React.ReactElement {
    const { classes } = this.props;
    
    if (this.state.isLoading) {
      return (
        <Box className={classes.loadingContainer}>
          <CircularProgress size={60} />
          <Typography variant="h6" style={{ marginTop: 16 }}>
            Loading files...
          </Typography>
        </Box>
      );
    }

    const { directories, files } = nullthrows(this.state.data);
    const directoryListItems = directories.map((directory) => (
      <DirectoryListItem
        directory={directory}
        key={directory.dirname}
        classes={classes}
        onSelect={(dirname) =>
          this.setState(
            (state, _props) => ({
              isLoading: true,
              path: `${state.path}${dirname}/`,
              data: undefined,
            }),
            async () => await this.refresh()
          )
        }
      />
    ));
    const fileListItems = files.map((file) => (
      <FileListItem
        file={file}
        key={file.filename}
        classes={classes}
        onDelete={async () => await this.refresh()}
      />
    ));

    const parentDirectoryItem =
      this.state.path !== "" ? (
        <DirectoryListItem
          directory={{ dirname: ".." }}
          key=".."
          classes={classes}
          onSelect={(_) =>
            this.setState(
              (state, _props) => ({
                isLoading: true,
                path: state.path.replace(/[^/]+\/$/, ""),
                data: undefined,
              }),
              async () => await this.refresh()
            )
          }
        />
      ) : null;

    return (
      <List>
        {parentDirectoryItem}
        {directoryListItems}
        {fileListItems}
      </List>
    );
  }

  render(): React.ReactElement {
    const { classes } = this.props;
    
    return (
      <Card className={classes.modernCard} elevation={0}>
        <CardHeader
          title={
            <Box display="flex" alignItems="center">
              <FolderIcon style={{ marginRight: 12, fontSize: 32 }} />
              <Typography variant="h4" style={{ fontWeight: 700, marginBottom: 4 }}>
                File Manager
              </Typography>
            </Box>
          }
          subheader={
            <Typography variant="subtitle1" color="textSecondary">
              Current path: {this.state.path || '/'}
            </Typography>
          }
          action={
            <UploadButton onUploadFinished={async () => await this.refresh()} />
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

export default withStyles(styles)(withAPI(FileList));
