import os
import torch
import torchvision
import numpy as np
import torch.nn as nn
from torchvision import transforms
from torchvision.utils import save_image

CUDA_VISIBLE_DEVICES=0
# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Hyper-parameters
latent_size = 100
hidn1=100
hidn2=100
image_size = 784
num_epochs = 200
batch_size = 100
sample_dir = 'samples'

# Create a directory if not exists
if not os.path.exists(sample_dir):
    os.makedirs(sample_dir)

# Image processing
transform = transforms.Compose([
                transforms.ToTensor(),
                transforms.Normalize(mean=(0.5, 0.5, 0.5),   # 3 for RGB channels
                                     std=(0.5, 0.5, 0.5))])

# MNIST dataset
mnist = torchvision.datasets.MNIST(root='../../data/',
                                   train=True,
                                   transform=transform,
                                   download=True)
test_mnist = torchvision.datasets.MNIST(root='../../data/',
                                   train=False,
                                   transform=transform,
                                   download=True)
# Data loader
data_loader = torch.utils.data.DataLoader(dataset=mnist,
                                          batch_size=batch_size, 
                                          shuffle=True)

test_loader = torch.utils.data.DataLoader(dataset=test_mnist,
                                          batch_size=len(test_mnist), 
                                          shuffle=True)

# Discriminator
class Dnet(nn.Module):
    def __init__(self):
        super(Dnet,self).__init__()
        self.hid1=nn.Sequential(
            nn.Linear(784,hidn1),
            nn.LeakyReLU(0.2),
            nn.Linear(hidn1,hidn2),
            nn.LeakyReLU(0.2),
            nn.Linear(hidn2,10),
            nn.Softmax()
            )
        self.hid2=nn.Sequential(
            nn.Linear(784,hidn1),
            nn.LeakyReLU(0.2),
            nn.Linear(hidn1,hidn2),
            nn.LeakyReLU(0.2),
            nn.Linear(hidn2,1),
            nn.Sigmoid()
            )
    def forward(self,input):
        out=torch.cat([self.hid1(input),self.hid2(input)],dim=1)
        return out

class Gnet(nn.Module):
    def __init__(self):
        super(Gnet,self).__init__()
        self.hid1=nn.Sequential(
            nn.Linear(latent_size+10 ,hidn1),
            nn.LeakyReLU(0.2),
            nn.Linear(hidn1,hidn2),
            nn.LeakyReLU(0.2),
            nn.Linear(hidn2,784),
            nn.Tanh()
            )
    def forward(self,input):
         return self.hid1(input)

G=Gnet()
D=Dnet()

if(os.path.isfile("G.ckpt")):
    print("Generator load")
    G=torch.load('G.ckpt')
if(os.path.isfile("D.ckpt")):
    print("Discriminator load")
    D=torch.load('D.ckpt')

# Device setting
D = D.to(device)
G = G.to(device)

# Binary cross entropy loss and optimizer
criterion = nn.BCELoss().cuda()
d_optimizer = torch.optim.Adam(D.parameters(), lr=0.000002)
g_optimizer = torch.optim.Adam(G.parameters(), lr=0.002)

def denorm(x):
    out = (x + 1) / 2
    return out.clamp(0, 1)

def reset_grad():
    d_optimizer.zero_grad()
    #g_optimizer.zero_grad()

# Start training
total_step = len(data_loader)
for epoch in range(num_epochs):
    
    for i, (images, targets) in enumerate(data_loader):
        batch_zeros=torch.zeros(batch_size,10)
        images = images.reshape(batch_size, -1).to(device)

        real_labels = torch.ones(batch_size, 1).to(device)
        fake_labels = torch.zeros(batch_size, 1).to(device)

        onehot=batch_zeros.scatter(1, targets.reshape(batch_size,1) ,1).to(device)
        outputs = D(images)

        real_labels=torch.cat([onehot,real_labels],dim=1)
        
        d_loss_real = criterion(outputs, real_labels)
        real_score = outputs.index_select(1,torch.Tensor([10]).long().cuda())
        
        
        rdint=np.random.random_integers(0,9,(batch_size))
        id=torch.Tensor(rdint).long()

        id_onehot=batch_zeros.scatter_(1,id.reshape(batch_size,1),1).to(device)

        fake_labels=torch.cat([id_onehot,fake_labels],dim=1)
        
        rd = torch.randn(batch_size, latent_size).to(device)
        rd = torch.cat([id_onehot,rd],dim=1)
        fake_images = G(rd)
        outputs = D(fake_images)
        d_loss_fake = criterion(outputs, fake_labels)
        fake_score = outputs.index_select(1,torch.Tensor([10]).long().cuda())
        
        d_loss = d_loss_real + d_loss_fake
        reset_grad()

        if(fake_score.mean().item()>0.5):
            d_loss.backward()
            d_optimizer.step()
        
        z = torch.randn(batch_size, latent_size).to(device)
        z=torch.cat([id_onehot,z],dim=1)
        fake_images = G(z)
        outputs = D(fake_images)

        g_loss = criterion(outputs, real_labels)
        
        reset_grad()

        g_loss.backward()
        g_optimizer.step()
        
        if ((i+1) % 200 == 0):
            print('Epoch [{}/{}], Step [{}/{}], d_loss: {:.4f}, g_loss: {:.4f}, D(x): {:.2f}, D(G(z)): {:.2f}' 
                  .format(epoch, num_epochs, i+1, total_step, d_loss.item(), g_loss.item(), 
                          real_score.mean().item(), fake_score.mean().item()))
            if(torch.isnan(d_loss).item()==0 and torch.isnan(g_loss).item()==0):
                torch.save(G, 'G.ckpt')
                torch.save(D, 'D.ckpt')
            for _, (images_, targets_) in enumerate(test_loader):
                test_zeros=torch.zeros((len(test_mnist),10))
                result = D(images_.reshape(len(test_mnist),-1).to(device))
                indices = torch.tensor([0,1,2,3,4,5,6,7,8,9]).to(device)
                result = torch.index_select(result, 1, indices)
                error = criterion(result,test_zeros.scatter_(1, targets_.reshape(-1,1) ,1).to(device))
                ans = torch.sum(torch.eq(torch.argmax(result,dim=1),targets_.reshape(-1).to(device)))
                print("classification accuracy = ",ans.item()/len(test_mnist)," error = ",error.item())
    if (epoch+1) == 1:
        images = images.reshape(images.size(0), 1, 28, 28)
        save_image(denorm(images), os.path.join(sample_dir, 'real_images.png'))
    fake_images = fake_images.reshape(fake_images.size(0), 1, 28, 28)
    save_image(denorm(fake_images), os.path.join(sample_dir, 'fake_images-{}.png'.format(epoch+1)))

torch.save(G, 'G.ckpt')
torch.save(D, 'D.ckpt')